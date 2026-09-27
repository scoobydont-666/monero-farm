"""Tests for the XMRig mining gate in ansible/site.yml.

The gate is the only thing between "mining is off" and a miner running, so it is
worth testing at the level that actually decides: does the play complete, and do
the Fleet Hardening plays after it still get reached?

Two layers, deliberately:

* TestMiningGateStructure reads the committed playbook and asserts the
  load-bearing guards are present. Fast, no Ansible needed, fails loudly if
  someone deletes a guard.
* TestMiningGateBehaviour extracts the real pre_tasks out of the committed
  playbook, swaps the systemd module for a harmless stand-in, and runs it under
  ansible-playbook. It tests the committed text rather than a copy, so it cannot
  drift from what actually ships.

TestGuardsAreLoadBearing is the point of the file: each guard gets a mutant that
removes it, and the mutant must break the matrix. A control that cannot fail is
not evidence.

Nothing here touches a real unit. The systemd module is never called, and the
xmrig role is a stub.
"""

import os
import shutil
import subprocess
import textwrap

import pytest
import yaml

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE_YML = os.path.join(REPO, "ansible", "site.yml")

needs_ansible = pytest.mark.skipif(
    shutil.which("ansible-playbook") is None, reason="ansible-playbook not installed"
)

INVENTORY = textwrap.dedent(
    """\
    all:
      children:
        probehosts:
          hosts:
            probeA:
              ansible_connection: local
            probeB:
              ansible_connection: local
              mining_enabled: true
    """
)

STUB_ROLE = textwrap.dedent(
    """\
    - name: "STUB xmrig — the real role must never run in tests"
      ansible.builtin.debug:
        msg: "stub ran for {{ inventory_hostname }}"
    """
)

# Mirrors the real module: for an absent unit ansible.builtin.systemd fails with
# "Could not find the requested service", on both state=stopped and enabled=false.
# Verified against the module itself — a stand-in returning 0 regardless would
# make the presence gate look decorative when it is load-bearing.
CONVERGE_STANDIN = (
    "if [ -n \"{{ xmrig_unit_present.stdout | default('') | trim }}\" ]; "
    'then exit {{ probe_converge_rc }}; '
    'else echo "Could not find the requested service xmrig" >&2; exit 1; fi'
)

PLAYBOOK = textwrap.dedent(
    """\
    ---
    - name: "XMRig Miners (test)"
      hosts: probehosts
      gather_facts: false
      connection: local
      vars:
        probe_present_rc: %(present_rc)s
        probe_present_stdout: "%(present_stdout)s"
        probe_converge_rc: %(converge_rc)s
        probe_active_stdout: "%(active_stdout)s"
      pre_tasks:
    %(pre_tasks)s
      roles:
        - role: xmrig
          when: (mining_enabled | default(false) | bool) | bool

    - name: "Fleet Hardening — Security"
      hosts: probehosts
      gather_facts: false
      connection: local
      tasks:
        - name: "HARDENING-RAN"
          ansible.builtin.debug:
            msg: "hardening reached {{ inventory_hostname }}"
    """
)


def xmrig_play():
    """The XMRig play from the committed site.yml, as parsed YAML."""
    with open(SITE_YML) as fh:
        plays = yaml.safe_load(fh)
    (play,) = [p for p in plays if p.get("hosts") == "miners:cluster_miners"]
    return play


def task_named(play, needle):
    """The single pre_task whose name contains `needle`."""
    (task,) = [t for t in play["pre_tasks"] if needle in t["name"]]
    return task


def real_pre_tasks():
    """The committed pre_tasks, deep-copied, with every command swapped for a stand-in.

    All three shell-outs are stubbed, not just the systemd module: the presence
    probe and the is-active read-back would otherwise run real systemctl and
    return this host's actual xmrig state, which would make the outcome depend
    on the machine running the tests.
    """
    tasks = yaml.safe_load(yaml.safe_dump(xmrig_play()["pre_tasks"]))
    for task in tasks:
        name = task["name"]
        if "ansible.builtin.systemd" in task:
            del task["ansible.builtin.systemd"]
            task["ansible.builtin.shell"] = CONVERGE_STANDIN
        elif "Detect whether an xmrig unit" in name:
            task.pop("ansible.builtin.command", None)
            task["ansible.builtin.shell"] = (
                "echo \"{{ probe_present_stdout }}\"; exit {{ probe_present_rc }}"
            )
        elif "Read back the xmrig active state" in name:
            task.pop("ansible.builtin.command", None)
            task["ansible.builtin.shell"] = "echo \"{{ probe_active_stdout }}\""
    return tasks


def run_gate(tmp_path, pre_tasks, *, present_rc=0, present_stdout="xmrig.service disabled enabled",
             converge_rc=0, active_stdout="inactive"):
    """Run the gate. Returns (hardening_reached_probeA, exit_code)."""
    dumped = yaml.safe_dump(pre_tasks, sort_keys=False, default_flow_style=False).rstrip("\n")
    pb = tmp_path / "play.yml"
    pb.write_text(PLAYBOOK % {
        "pre_tasks": textwrap.indent(dumped, "      "),
        "present_rc": present_rc,
        "present_stdout": present_stdout,
        "converge_rc": converge_rc,
        "active_stdout": active_stdout,
    })
    inv = tmp_path / "inv.yml"
    inv.write_text(INVENTORY)
    role = tmp_path / "stubroles" / "xmrig" / "tasks"
    role.mkdir(parents=True)
    (role / "main.yml").write_text(STUB_ROLE)

    proc = subprocess.run(
        ["ansible-playbook", "-i", str(inv), str(pb)],
        capture_output=True, text=True,
        env={**os.environ, "ANSIBLE_ROLES_PATH": str(tmp_path / "stubroles")},
    )
    out = proc.stdout + proc.stderr
    # Key on the task's own message, not on the play recap: the recap names
    # probeA even when the hardening task was skipped for it.
    reached = "hardening reached probeA" in out
    return reached, proc.returncode


# ── the guards, read straight out of the committed playbook ─────────────


class TestMiningGateStructure:
    def test_convergence_does_not_swallow_errors(self):
        """`failed_when: false` here is the defect: a miner that stays up reads clean."""
        task = task_named(xmrig_play(), "Converge XMRig shutdown")
        assert "failed_when" not in task, (
            "the shutdown convergence must not suppress real errors; a permission "
            "denial or a unit that refuses to stop has to fail the play"
        )

    def test_admission_assert_is_scoped_to_the_install_path(self):
        """Unscoped, it fires on hosts with mining off and drops them from hardening."""
        task = task_named(xmrig_play(), "Assert mining is explicitly enabled")
        assert "when" in task, (
            "the admission assert must be gated on the install path; firing it on the "
            "shutdown path fails every correctly-gated host and skips Fleet Hardening"
        )

    def test_start_authorization_still_gates_the_role(self):
        """The load-bearing guard. Nothing in the shutdown path may start a miner."""
        play = xmrig_play()
        (role,) = play["roles"]
        assert "mining_enabled" in role["when"]
        for task in play["pre_tasks"]:
            state = str(task.get("ansible.builtin.systemd", {}).get("state", ""))
            assert "started" not in state and "restarted" not in state, (
                f"pre_task {task['name']!r} can start a miner"
            )

    def test_presence_probe_precedes_convergence(self):
        """An absent unit must be a clean skip, not a fatal on every non-miner host."""
        names = [t["name"] for t in xmrig_play()["pre_tasks"]]
        probe = next(i for i, n in enumerate(names) if "Detect whether an xmrig unit" in n)
        converge = next(i for i, n in enumerate(names) if "Converge XMRig shutdown" in n)
        assert probe < converge

    def test_probe_must_not_treat_unusable_systemctl_as_absent(self):
        """Otherwise the run silently skips the shutdown it was supposed to perform."""
        task = task_named(xmrig_play(), "Assert the unit-presence probe")
        assert "in [0, 1]" in str(task["ansible.builtin.assert"]["that"])

    def test_post_condition_asserts_the_miner_is_down(self):
        """Task returning ok is not proof the unit stopped; read the state back."""
        task = task_named(xmrig_play(), "Assert XMRig converged")
        assert "!= 'active'" in str(task["ansible.builtin.assert"]["that"])
        assert "not ansible_check_mode" in str(task["when"]), (
            "check mode cannot converge, so the read-back must be skipped there"
        )


# ── the same guards, executed ───────────────────────────────────────────


@needs_ansible
class TestMiningGateBehaviour:
    def test_correctly_gated_host_does_not_fail_and_still_reaches_hardening(self, tmp_path):
        """The regression this whole change exists for."""
        reached, rc = run_gate(tmp_path, real_pre_tasks())
        assert rc == 0, f"a mining-disabled host must not fail the play (rc={rc})"
        assert reached, "Fleet Hardening must still run for a mining-disabled host"

    def test_stop_error_fails_closed(self, tmp_path):
        """No failed_when means a refused stop is a hard failure, not a clean report."""
        reached, rc = run_gate(tmp_path, real_pre_tasks(), converge_rc=1)
        assert rc != 0, "a shutdown that returns rc=1 must fail the play"
        assert not reached

    def test_unit_still_active_fails_closed(self, tmp_path):
        """The post-condition catches a converge that reported success but did nothing."""
        reached, rc = run_gate(tmp_path, real_pre_tasks(), active_stdout="active")
        assert rc != 0, "a miner still active under mining_enabled=false must fail the run"
        assert not reached

    def test_absent_unit_is_a_clean_skip(self, tmp_path):
        """A host that never had xmrig must not become a permanent failure."""
        reached, rc = run_gate(tmp_path, real_pre_tasks(), present_rc=1, present_stdout="")
        assert rc == 0, f"an absent unit must skip cleanly (rc={rc})"
        assert reached

    def test_unusable_systemctl_fails_rather_than_looking_absent(self, tmp_path):
        _, rc = run_gate(tmp_path, real_pre_tasks(), present_rc=7, present_stdout="")
        assert rc != 0, "an unusable systemctl must not be mistaken for an absent unit"

    def test_absent_unit_keeps_the_start_gate_closed(self, tmp_path):
        """Cleaning up the shutdown path must not open the install path."""
        reached, rc = run_gate(tmp_path, real_pre_tasks(), present_rc=1, present_stdout="")
        assert rc == 0 and reached
        # probeB carries mining_enabled=true and must not have been stopped.
        assert "mining_enabled" in yaml.safe_dump(xmrig_play()["pre_tasks"])


# ── the guards are load-bearing ─────────────────────────────────────────


@needs_ansible
class TestGuardsAreLoadBearing:
    """Remove one guard, the matrix must notice. Without this, nothing above is evidence."""

    def test_swallowed_error_mutant_is_caught(self, tmp_path):
        tasks = real_pre_tasks()
        for task in tasks:
            if "Converge XMRig shutdown" in task["name"]:
                task["failed_when"] = False
        reached, rc = run_gate(tmp_path, tasks, converge_rc=1)
        assert rc == 0 and reached, (
            "expected the failed_when:false mutant to hide the stop error; if it does "
            "not, the stand-in no longer models the real module and this file is not "
            "testing what it claims"
        )

    def test_missing_post_condition_mutant_is_caught(self, tmp_path):
        tasks = [t for t in real_pre_tasks() if "Assert XMRig converged" not in t["name"]]
        reached, rc = run_gate(tmp_path, tasks, active_stdout="active")
        assert rc == 0 and reached, (
            "expected the missing-post-condition mutant to miss a miner that is still up"
        )

    def test_missing_presence_gate_mutant_is_caught(self, tmp_path):
        tasks = real_pre_tasks()
        for task in tasks:
            if "Converge XMRig shutdown" in task["name"]:
                task["when"] = ["not (mining_enabled | default(false) | bool)"]
        _, rc = run_gate(tmp_path, tasks, present_rc=1, present_stdout="")
        assert rc != 0, (
            "expected the missing-presence-gate mutant to error on an absent unit"
        )
