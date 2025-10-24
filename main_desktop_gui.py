#!/usr/bin/env python3
import os
import sys
import subprocess
from pathlib import Path


def is_already_running():
    """Check if another instance is already running."""
    try:
        import psutil
        current_pid = os.getpid()
        script_path = str(Path(__file__).resolve())
        
        for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'exe']):
            try:
                # Skip current process
                if proc.info['pid'] == current_pid:
                    continue
                
                cmdline = proc.info.get('cmdline') or []
                exe = proc.info.get('exe') or ''
                
                # Check if it's a Python process
                if not ('python' in exe.lower() or any('python' in str(arg).lower() for arg in cmdline[:2])):
                    continue
                
                # Check if it's running this exact script
                # Look for the script path in cmdline (not just the name)
                for arg in cmdline:
                    arg_str = str(arg)
                    # Match exact script path or if running via uv/python with this script
                    if script_path in arg_str or (arg_str.endswith('main_desktop_gui.py') and 'lsp_server' not in ' '.join(cmdline)):
                        return True
                        
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
    except ImportError:
        # psutil not available, skip check
        pass
    return False


def start_detached():
    """Start the application detached from terminal using subprocess."""
    # Create log file for debugging
    log_dir = Path.home() / ".local" / "share" / "audio-record"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "dictafono.log"
    
    # Get the Python executable (from venv if available)
    python_exe = sys.executable
    script_path = str(Path(__file__).resolve())
    
    # Open log file
    log_fd = open(log_file, 'a')
    
    # Start process detached
    process = subprocess.Popen(
        [python_exe, script_path, '--no-detach'],
        stdout=log_fd,
        stderr=log_fd,
        stdin=subprocess.DEVNULL,
        start_new_session=True,  # This detaches from terminal
        cwd=str(Path(__file__).resolve().parent),  # run from project root to keep relative paths working
    )
    
    print(f"Dictáfono iniciado en segundo plano (PID: {process.pid})")
    print(f"Logs en: {log_file}")
    
    # Don't wait for the process
    return 0


def main():
    """Entry point with detach support."""
    # Check for --no-detach flag
    no_detach = '--no-detach' in sys.argv or '--foreground' in sys.argv or '-f' in sys.argv
    
    # Check for --help flag
    if '--help' in sys.argv or '-h' in sys.argv:
        print("Uso: main_desktop_gui.py [opciones]")
        print("\nOpciones:")
        print("  --no-detach, --foreground, -f    Ejecutar en primer plano (no desacoplar)")
        print("  --help, -h                       Mostrar esta ayuda")
        print("\nPor defecto, el programa se ejecuta en segundo plano.")
        return 0
    
    # If running in detached mode, start via subprocess
    if not no_detach:
        # Check if already running
        if is_already_running():
            print("El dictáfono ya está en ejecución.")
            return 1
        
        return start_detached()
    
    # Running in foreground mode - import and run the main application
    from app.main import main as app_main
    return app_main()


if __name__ == "__main__":
    raise SystemExit(main())