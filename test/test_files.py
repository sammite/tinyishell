import subprocess
import os
import hashlib
import pytest

def get_file_hash(path):
    """Computes SHA256 hash of a file."""
    hasher = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hasher.update(chunk)
    return hasher.hexdigest()

def test_put_get_integrity(tshd_daemon, tmp_path):
    config = tshd_daemon
    
    # 1. Create a local file with specific content
    content = "test_content_for_integrity_check"
    local_file = tmp_path / "tmpfile"
    local_file.write_text(content)
    
    remote_path = "/var/tmp"
    remote_file = "/var/tmp/tmpfile"
    
    # 2. Put the file to the remote server
    put_res = subprocess.run([config["tsh_path"], "-s", config["secret"], "localhost", "put", str(local_file), remote_path],
                             capture_output=True, text=True)
    assert put_res.returncode == 0
    
    # 3. Get the file back
    get_res = subprocess.run([config["tsh_path"], "-s", config["secret"], "localhost", "get", remote_file, str(tmp_path)],
                             capture_output=True, text=True)
    assert get_res.returncode == 0
    
    # Check integrity
    downloaded_file = tmp_path / "tmpfile"
    assert downloaded_file.read_text() == content
    
    # 4. Cleanup remote file via exec
    subprocess.run([config["tsh_path"], "-s", config["secret"], "localhost", "exec", f"/bin/rm -f {remote_file}"])

@pytest.mark.parametrize("size_kb", [1, 64, 1024]) # 1KB, 64KB, 1MB
def test_large_file_integrity(tshd_daemon, tmp_path, size_kb):
    config = tshd_daemon
    local_file = tmp_path / f"large_test_{size_kb}kb"
    remote_path = "/var/tmp"
    remote_file = f"/var/tmp/large_test_{size_kb}kb"
    
    # 1. Generate local file with random data
    subprocess.run(["head", "-c", str(size_kb * 1024), "/dev/urandom"], 
                   stdout=open(local_file, "wb"))
    original_hash = get_file_hash(local_file)
    
    # 2. Put to remote
    subprocess.run([config["tsh_path"], "-s", config["secret"], "localhost", "put", str(local_file), remote_path],
                   check=True, capture_output=True)
    
    # 3. Get back to a new local path
    download_dir = tmp_path / "downloaded"
    download_dir.mkdir()
    subprocess.run([config["tsh_path"], "-s", config["secret"], "localhost", "get", remote_file, str(download_dir)],
                   check=True, capture_output=True)
    
    downloaded_file = download_dir / f"large_test_{size_kb}kb"
    downloaded_hash = get_file_hash(downloaded_file)
    
    # 4. Validate
    assert original_hash == downloaded_hash
    
    # 5. Cleanup
    subprocess.run([config["tsh_path"], "-s", config["secret"], "localhost", "exec", f"/bin/rm -f {remote_file}"])
