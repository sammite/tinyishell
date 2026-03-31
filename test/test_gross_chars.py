import os
import subprocess
import pytest
import shutil
import hashlib

def get_file_hash(path):
    hasher = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hasher.update(chunk)
    return hasher.hexdigest()

@pytest.mark.parametrize("gross_name", [
    "gross_!@#$%^&()_+=-[]{};'\", .txt",
    "name with spaces",
    "shell_meta_;&|<>",
    "quotes_\"'\"",
    "backslashes_\\\\",
    "dots_.._and_..._dots",
    "tsh_is_nasty_\t_tab",
    # Newline is often too gross for many tools, but let's try it if OS allows
    "newline_\n_char"
])
def test_gross_filename_integrity(tshd_daemon, tmp_path, gross_name):
    """
    Test that tsh can put, ls, and get files with 'gross' characters.
    """
    config = tshd_daemon
    remote_dir = "/var/tmp/gross_test"
    
    # 1. Create remote dir if it doesn't exist
    if not os.path.exists(remote_dir):
        os.makedirs(remote_dir, exist_ok=True)
        
    local_file = tmp_path / gross_name
    content = f"Content for {gross_name}"
    
    try:
        # 2. Write local file
        local_file.write_text(content)
    except OSError as e:
        pytest.skip(f"OS does not support filename: {repr(gross_name)} - {e}")
        
    original_hash = get_file_hash(local_file)
    
    try:
        # 3. Put
        # tsh -s <secret> localhost put <source> <dest_dir>
        res = subprocess.run([config["tsh_path"], "-s", config["secret"], "localhost", "put", str(local_file), remote_dir],
                             capture_output=True, text=True)
        assert res.returncode == 0, f"Put failed for {repr(gross_name)}: {res.stderr}"
        
        # 4. LS
        res = subprocess.run([config["tsh_path"], "-s", config["secret"], "localhost", "ls", remote_dir],
                             capture_output=True, text=True)
        assert res.returncode == 0
        # Check if the filename is in the output
        assert gross_name in res.stdout, f"Filename {repr(gross_name)} not found in ls output:\n{res.stdout}"
        
        # 5. Get
        download_dir = tmp_path / "download"
        download_dir.mkdir(exist_ok=True)
        remote_path = os.path.join(remote_dir, gross_name)
        
        res = subprocess.run([config["tsh_path"], "-s", config["secret"], "localhost", "get", remote_path, str(download_dir)],
                             capture_output=True, text=True)
        assert res.returncode == 0, f"Get failed for {repr(gross_name)}: {res.stderr}"
        
        downloaded_file = download_dir / gross_name
        assert downloaded_file.exists()
        assert get_file_hash(downloaded_file) == original_hash
        
    finally:
        # Cleanup remote
        p = os.path.join(remote_dir, gross_name)
        if os.path.exists(p):
            os.remove(p)

def test_gross_directory_creation(tshd_daemon):
    """
    Test LS on a directory with gross characters.
    """
    config = tshd_daemon
    gross_dir = "/var/tmp/gross_dir_!@#$%^&()_+ "
    
    if os.path.exists(gross_dir):
        shutil.rmtree(gross_dir)
    os.makedirs(gross_dir)
    
    try:
        # Test LS
        res = subprocess.run([config["tsh_path"], "-s", config["secret"], "localhost", "ls", gross_dir],
                             capture_output=True, text=True)
        assert res.returncode == 0
        assert "." in res.stdout
        assert ".." in res.stdout
        
    finally:
        if os.path.exists(gross_dir):
            shutil.rmtree(gross_dir)
