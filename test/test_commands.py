import subprocess
import pytest

def test_ls_root_and_home(tshd_daemon):
    config = tshd_daemon
    
    # Test ls /
    res_root = subprocess.run([config["tsh_path"], "-s", config["secret"], "localhost", "ls", "/"], 
                              capture_output=True, text=True)
    print(f"\n[DEBUG] ls / stdout:\n{res_root.stdout}")
    assert res_root.returncode == 0
    assert "etc" in res_root.stdout

    # Test ls /home
    res_home = subprocess.run([config["tsh_path"], "-s", config["secret"], "localhost", "ls", "/home"], 
                              capture_output=True, text=True)
    print(f"\n[DEBUG] ls /home stdout:\n{res_home.stdout}")
    assert res_home.returncode == 0

def test_exec_touch_verification(tshd_daemon):
    config = tshd_daemon
    target_file = "/var/tmp/touched_by_pytest"
    
    # Ensure file doesn't exist first (via exec rm)
    subprocess.run([config["tsh_path"], "-s", config["secret"], "localhost", "exec", f"/bin/rm -f {target_file}"])
    
    # Run touch
    res_touch = subprocess.run([config["tsh_path"], "-s", config["secret"], "localhost", "exec", f"/usr/bin/touch {target_file}"],
                               capture_output=True, text=True)
    print(f"\n[DEBUG] exec touch stdout:\n{res_touch.stdout}")
    assert "Exit code: 0" in res_touch.stdout
    
    # Verify via ls
    res_ls = subprocess.run([config["tsh_path"], "-s", config["secret"], "localhost", "ls", "/var/tmp"],
                            capture_output=True, text=True)
    print(f"\n[DEBUG] ls /var/tmp verification stdout:\n{res_ls.stdout}")
    assert "touched_by_pytest" in res_ls.stdout
    
    # Cleanup
    subprocess.run([config["tsh_path"], "-s", config["secret"], "localhost", "exec", f"/bin/rm -f {target_file}"])
