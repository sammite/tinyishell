import subprocess
import pytest
import os

# List to track failed command lines for final reporting
failed_exec_commands = []

@pytest.fixture(scope="module", autouse=True)
def exec_failure_reporter():
    """Prints a summary of failed command lines at the end of the module."""
    yield
    if failed_exec_commands:
        print("\n" + "="*40)
        print("SUMMARY OF FAILED EXECUTION COMMANDS:")
        for cmd_str in failed_exec_commands:
            print(f"  {cmd_str}")
        print("="*40)

@pytest.mark.parametrize("command, expected_exit", [
    ("/usr/bin/true", 0),
    ("/usr/bin/false", 1),
    ("/usr/bin/touch /var/tmp/exec_test", 0),
    ("/usr/bin/rm /var/tmp/exec_test", 0),
    ("/usr/bin/sleep 0.1", 0),
])
def test_exec_exit_codes(tshd_daemon, command, expected_exit):
    config = tshd_daemon
    full_cmd = [config["tsh_path"], "-s", config["secret"], "localhost", "exec", command]
    result = subprocess.run(full_cmd, capture_output=True, text=True)
    
    print(f"\n[DEBUG] exec '{command}' stdout:\n{result.stdout}")
    
    exit_msg = f"Exit code: {expected_exit}"
    if exit_msg not in result.stdout:
        failed_exec_commands.append(" ".join(full_cmd))
        assert exit_msg in result.stdout

def test_exec_touch_side_effect(tshd_daemon):
    config = tshd_daemon
    target = "/var/tmp/exec_battery_touch"
    
    # 1. Cleanup first
    subprocess.run([config["tsh_path"], "-s", config["secret"], "localhost", "exec", f"/usr/bin/rm -f {target}"])
    
    # 2. Run touch
    full_cmd = [config["tsh_path"], "-s", config["secret"], "localhost", "exec", f"/usr/bin/touch {target}"]
    result = subprocess.run(full_cmd, capture_output=True, text=True)
    print(f"\n[DEBUG] exec touch stdout:\n{result.stdout}")
    
    if "Exit code: 0" not in result.stdout:
        failed_exec_commands.append(" ".join(full_cmd))
        assert "Exit code: 0" in result.stdout
    
    # 3. Verify via ls
    ls_cmd = [config["tsh_path"], "-s", config["secret"], "localhost", "ls", "/var/tmp"]
    ls_result = subprocess.run(ls_cmd, capture_output=True, text=True)
    print(f"\n[DEBUG] ls verification stdout:\n{ls_result.stdout}")
    assert "exec_battery_touch" in ls_result.stdout
    
    # 4. Cleanup
    subprocess.run([config["tsh_path"], "-s", config["secret"], "localhost", "exec", f"/usr/bin/rm -f {target}"])
