import os
import sys
import zipfile
from datetime import datetime

def package_manifest():
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_name = f"Manifest-Clean-{timestamp}.zip"
    zip_path = os.path.join(root_dir, zip_name)

    # Clean up old zip files in root
    for f in os.listdir(root_dir):
        if f.startswith("Manifest-Clean-") and f.endswith(".zip"):
            try:
                os.remove(os.path.join(root_dir, f))
            except Exception:
                pass

    include_dirs = ["notetrace_backend", "static", "termux", "scripts"]
    include_files = [
        "run.py", "run.bat", "requirements.txt", "README.md",
        "1-Click-Tablet.bat", "Sync-To-Tablet.bat", "Setup-SSH-Key.bat"
    ]

    print(f"[*] Packaging into {zip_name}...")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in include_files:
            fp = os.path.join(root_dir, f)
            if os.path.exists(fp):
                zf.write(fp, f)
        
        for d in include_dirs:
            dp = os.path.join(root_dir, d)
            if os.path.exists(dp):
                for root, _, files in os.walk(dp):
                    if "__pycache__" in root or ".pytest_cache" in root:
                        continue
                    for file in files:
                        if file.endswith(".zip") or file.endswith(".tar.gz"):
                            continue
                        full_p = os.path.join(root, file)
                        rel_p = os.path.relpath(full_p, root_dir)
                        zf.write(full_p, rel_p.replace("\\", "/"))

    size_mb = os.path.getsize(zip_path) / (1024 * 1024)
    print(f"[✓] Created {zip_name} ({size_mb:.2f} MB)")
    
    # Return the created zip filename so caller knows it
    print(f"OUTPUT_ZIP={zip_name}")
    return zip_name

if __name__ == "__main__":
    package_manifest()
