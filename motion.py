import os
import subprocess
import urllib.request
import zipfile
import shutil
import argparse
import sys

# --- YAPILANDIRMA ---
PYTHON_VER = "3.11.5"
MOTION_ROOT = os.path.join(os.environ['TEMP'], "Motion")
CACHE_DIR = os.path.join(MOTION_ROOT, f"Python{PYTHON_VER.replace('.', '')[:2]}")
BUILD_DIR = os.path.join(MOTION_ROOT, "CurrentBuild")

TERMINAL_DIR = os.environ.get("REAL_CWD", os.getcwd())
NET_PATH = r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319"
CSC_PATH = os.path.join(NET_PATH, "csc.exe")

def setup_env(main_py):
    main_py_abs = os.path.abspath(main_py)
    if not os.path.exists(main_py_abs):
        print(f"[!] Error: '{main_py}' does not exist.")
        sys.exit(1)

    if not os.path.exists(CACHE_DIR): os.makedirs(CACHE_DIR)
    if os.path.exists(BUILD_DIR): shutil.rmtree(BUILD_DIR)
    os.makedirs(BUILD_DIR)

    # 1. Python Çekirdeği (Cache)
    py_exe_cache = os.path.join(CACHE_DIR, "python.exe")
    if not os.path.exists(py_exe_cache):
        print(f"[*] Installing Python {PYTHON_VER}...")
        url = f"https://www.python.org/ftp/python/{PYTHON_VER}/python-{PYTHON_VER}-embed-amd64.zip"
        zip_p = os.path.join(CACHE_DIR, "p.zip")
        urllib.request.urlretrieve(url, zip_p)
        with zipfile.ZipFile(zip_p, 'r') as z: z.extractall(CACHE_DIR)
        os.remove(zip_p)

    # 2. Build Klasörüne Kopyala
    for item in os.listdir(CACHE_DIR):
        src = os.path.join(CACHE_DIR, item)
        dst = os.path.join(BUILD_DIR, item)
        if os.path.isdir(src): shutil.copytree(src, dst)
        else: shutil.copy2(src, dst)

    # 3. ._pth DOSYASINI ÖNCEDEN OLUŞTUR (Pip için kritik)
    py_short = "".join(PYTHON_VER.split(".")[:2])
    with open(os.path.join(BUILD_DIR, f"python{py_short}._pth"), "w") as f:
        f.write(".\n")
        f.write(f"python{py_short}.zip\n")
        f.write("site-packages\n")
        f.write("import site\n")

    # 4. PIP VE KÜTÜPHANE YÜKLEME
    possible_reqs = [
        os.path.join(TERMINAL_DIR, "requirements.txt"),
        os.path.join(os.path.dirname(main_py_abs), "requirements.txt"),
    ]
    req_file = next((f for f in possible_reqs if os.path.exists(f)), None)
    py_exe = os.path.join(BUILD_DIR, "python.exe")
    site_packages = os.path.join(BUILD_DIR, "site-packages")
    if not os.path.exists(site_packages): os.makedirs(site_packages)

    if req_file:
        print(f"[*] Found requirements file: {req_file}")
        print(f"[*] Setting up pip...")
        gp_path = os.path.join(BUILD_DIR, "get-pip.py")
        urllib.request.urlretrieve("https://bootstrap.pypa.io/get-pip.py", gp_path)
        
        # Pip kurulumu
        subprocess.run([py_exe, gp_path, "--no-warn-script-location"], check=True)
        os.remove(gp_path)
        
        print(f"[*] Installing packages from pip...")
        # SSL hatalarını aşmak için trusted-host ekledik
        pip_cmd = [
            py_exe, "-m", "pip", "install", 
            "-r", req_file, 
            "--target", site_packages,
            "--no-cache-dir",
            "--trusted-host", "pypi.org",
            "--trusted-host", "files.pythonhosted.org",
            "--no-warn-script-location"
        ]
        
        # Hata takibi için çıktıyı yakalıyoruz
        result = subprocess.run(pip_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print("\n[!!!] PIP ERROR [!!!]")
            print(f"More info about error:\n{result.stderr}")
            sys.exit(1)
        else:
            print("[+] Packages successfully installed.")

    # 5. Proje Dosyalarını Kopyala
    print(f"[*] Packaging project files...")
    exclude = [".git", "__pycache__", "Motion"]
    base_src = os.path.dirname(main_py_abs)
    for item in os.listdir(base_src):
        if item in exclude or item.endswith(".exe"): continue
        s = os.path.join(base_src, item)
        d = os.path.join(BUILD_DIR, item)
        try:
            if os.path.isdir(s): shutil.copytree(s, d, dirs_exist_ok=True)
            else: shutil.copy2(s, d)
        except: pass
    
    main_filename = os.path.basename(main_py_abs)
    shutil.copy2(main_py_abs, os.path.join(BUILD_DIR, main_filename))
    return main_filename

def build(output_exe, main_filename, show_debug, is_hidden, icon_path):
    out_abs = os.path.join(TERMINAL_DIR, output_exe) if not os.path.isabs(output_exe) else output_exe
    payload_path = os.path.join(BUILD_DIR, "assets.dat")
    cs_path = os.path.join(BUILD_DIR, "launcher.cs")

    with zipfile.ZipFile(payload_path, 'w', zipfile.ZIP_STORED) as z:
        for root, dirs, files in os.walk(BUILD_DIR):
            for file in files:
                if file in ["assets.dat", "launcher.cs"]: continue
                fp = os.path.join(root, file)
                z.write(fp, os.path.relpath(fp, BUILD_DIR))

    target_type = "exe" if (show_debug or not is_hidden) else "winexe"
    hide_window = "true" if is_hidden and not show_debug else "false"
    
    cs_code = f"""
using System;
using System.IO;
using System.Diagnostics;
using System.Reflection;
using System.IO.Compression;

class Program {{
    static void Main(string[] args) {{
        try {{
            string realCwd = Environment.CurrentDirectory;
            string tempDir = Path.Combine(Path.GetTempPath(), "MotionRun_" + Guid.NewGuid().ToString("N").Substring(0,6));
            Directory.CreateDirectory(tempDir);
            
            Assembly a = Assembly.GetExecutingAssembly();
            string pkg = Path.Combine(tempDir, "data.pkg");
            using (Stream s = a.GetManifestResourceStream("AppData")) {{
                using (FileStream fs = new FileStream(pkg, FileMode.Create)) {{ s.CopyTo(fs); }}
            }}
            ZipFile.ExtractToDirectory(pkg, tempDir);
            File.Delete(pkg);

            Process p = new Process();
            p.StartInfo.FileName = Path.Combine(tempDir, "python.exe");
            p.StartInfo.Arguments = "-u \\"" + Path.Combine(tempDir, "{main_filename}") + "\\" " + string.Join(" ", args);
            p.StartInfo.EnvironmentVariables["REAL_CWD"] = realCwd;
            p.StartInfo.WorkingDirectory = tempDir; 
            p.StartInfo.UseShellExecute = false;
            p.StartInfo.CreateNoWindow = {hide_window};
            p.Start();
            p.WaitForExit();
            try {{ Directory.Delete(tempDir, true); }} catch {{}}
        }} catch {{}}
    }}
}}"""
    with open(cs_path, "w", encoding="utf-8") as f: f.write(cs_code)

    cmd = [
        CSC_PATH, f"/target:{target_type}", "/optimize",
        "/r:System.IO.Compression.FileSystem.dll", "/r:System.IO.Compression.dll",
        f"/resource:{payload_path},AppData", f"/out:{out_abs}", cs_path
    ]
    if icon_path and os.path.exists(icon_path):
        cmd.append(f"/win32icon:{os.path.abspath(icon_path)}")

    subprocess.run(cmd, capture_output=True)
    print(f"\n[+] {out_abs} successfully compiled.")
    
    if os.path.exists(payload_path): os.remove(payload_path)
    if os.path.exists(cs_path): os.remove(cs_path)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("script")
    parser.add_argument("-o", "--output")
    parser.add_argument("-d", "--debug", action="store_true")
    parser.add_argument("-s", "--silent", action="store_true")
    parser.add_argument("-i", "--icon")
    args = parser.parse_args()
    
    if not args.output:
        args.output = os.path.basename(args.script).replace(".py", ".exe")

    fname = setup_env(args.script)
    build(args.output, fname, args.debug, args.silent, args.icon)
