import os, sys, tempfile, subprocess
sys.path.insert(0, '/home/nixos/Projects/Nova')

diag = '/home/nixos/Projects/Nova/tmpdir_diag.txt'
with open(diag, 'w') as f:
    f.write("=== TMPDIR Diagnostic ===\n")
    for var in ['TMPDIR', 'TMP', 'TEMP', 'HOME', 'DISPLAY', 'WAYLAND_DISPLAY', 'XDG_RUNTIME_DIR']:
        f.write(f"{var}={os.environ.get(var, '<not set>')}\n")
    
    tmpdir = os.environ.get('TMPDIR', '/tmp')
    f.write(f"\nResolved TMPDIR: {tmpdir}\n")
    f.write(f"TMPDIR exists: {os.path.exists(tmpdir)}\n")
    f.write(f"TMPDIR writable: {os.access(tmpdir, os.W_OK)}\n")
    
    try:
        td = tempfile.mkdtemp(prefix='.chromium_test.', dir=tmpdir)
        f.write(f"mkdtemp OK: {td}\n")
        os.rmdir(td)
    except Exception as e:
        f.write(f"mkdtemp FAILED: {e}\n")
    
    # Now try launching Chromium with and without TMPDIR override
    from nova.utils import resolve_chromium_bin
    chromium = resolve_chromium_bin()
    f.write(f"\nChromium: {chromium}\n")
    
    # Test 1: With inherited env (service TMPDIR)
    f.write("\n--- Test 1: Inherited TMPDIR ---\n")
    proc = subprocess.Popen(
        [chromium, '--remote-debugging-port=9223',
         '--user-data-dir=/home/nixos/.config/nova-chromium-test',
         '--no-first-run', '--no-default-browser-check',
         '--ozone-platform=wayland', '--enable-features=UseOzonePlatform'],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL, start_new_session=True
    )
    import time; time.sleep(3)
    rc = proc.poll()
    if rc is not None:
        stderr = proc.stderr.read().decode('utf-8', errors='replace')[:500]
        f.write(f"DIED with code {rc}\nstderr: {stderr}\n")
    else:
        f.write(f"ALIVE PID={proc.pid}\n")
        proc.terminate()
    
    # Cleanup test profile
    subprocess.run(['rm', '-rf', '/home/nixos/.config/nova-chromium-test'], capture_output=True)
    
    # Test 2: With TMPDIR=/tmp 
    f.write("\n--- Test 2: TMPDIR=/tmp ---\n")
    env2 = os.environ.copy()
    env2['TMPDIR'] = '/tmp'
    env2['TMP'] = '/tmp'
    env2['TEMP'] = '/tmp'
    proc2 = subprocess.Popen(
        [chromium, '--remote-debugging-port=9223',
         '--user-data-dir=/home/nixos/.config/nova-chromium-test',
         '--no-first-run', '--no-default-browser-check',
         '--ozone-platform=wayland', '--enable-features=UseOzonePlatform'],
        env=env2,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL, start_new_session=True
    )
    time.sleep(3)
    rc2 = proc2.poll()
    if rc2 is not None:
        stderr2 = proc2.stderr.read().decode('utf-8', errors='replace')[:500]
        f.write(f"DIED with code {rc2}\nstderr: {stderr2}\n")
    else:
        f.write(f"ALIVE PID={proc2.pid}\n")
        proc2.terminate()
    
    subprocess.run(['rm', '-rf', '/home/nixos/.config/nova-chromium-test'], capture_output=True)
    f.write("\nDiagnostic complete\n")

print(f"Diagnostic written to {diag}")
