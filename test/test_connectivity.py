import subprocess

def test_connectivity(tshd_daemon):
    """Verifies that tsh can connect to tshd and perform a simple 'ls /'."""
    config = tshd_daemon
    
    # Run 'ls /' via tsh
    cmd = [config["tsh_path"], "-s", config["secret"], "localhost", "ls", "/"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    # Assert successful connection and listing
    print(f"\n[DEBUG] Connectivity test stdout:\n{result.stdout}")
    if result.stderr:
        print(f"[DEBUG] Connectivity test stderr:\n{result.stderr}")

    assert result.returncode == 0
    # Standard Linux root directories
    assert "etc" in result.stdout or "bin" in result.stdout
