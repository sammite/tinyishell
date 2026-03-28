import pytest
import subprocess
import os
import signal
import time

def pytest_addoption(parser):
    parser.addoption("--musl", action="store_true", help="run tests with musl static binaries")

@pytest.fixture(scope="session")
def build_tsh(request):
    """Builds tsh and tshd binaries once per session."""
    secret = "testkey"
    port = 1234
    
    # Determine target
    target = "linux_musl" if request.config.getoption("--musl") else "linux"
    
    # Clean and build
    subprocess.run(["make", "clean"], capture_output=True)
    cmd = ["make", target, f"SECRET_KEY={secret}", f"SERVER_PORT={port}"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        pytest.fail(f"Build failed: {result.stderr}")
        
    return {"secret": secret, "port": port, "tsh_path": "./tsh", "tshd_path": "./tshd", "target": target}

@pytest.fixture
def tshd_daemon(build_tsh):
    """Starts the tshd daemon and ensures it's killed after the test."""
    # Ensure no old daemon is running
    subprocess.run(["pkill", "tshd"], capture_output=True)
    
    # Start the daemon (it forks into background)
    subprocess.run([build_tsh["tshd_path"]])
    time.sleep(0.5) # Give it a moment to start
    
    yield build_tsh
    
    # Cleanup: Kill all tshd processes
    subprocess.run(["pkill", "tshd"], capture_output=True)
