import time
import os
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from trace.core.decompiler import decompiler
import threading

class TraceFileHandler(FileSystemEventHandler):
    def __init__(self, debounce_seconds=5.0):
        self.debounce_seconds = debounce_seconds
        self.timers = {}
        
    def on_modified(self, event):
        if event.is_directory or not event.src_path.endswith('.md'):
            return
            
        # Cancel existing timer if one exists
        if event.src_path in self.timers:
            self.timers[event.src_path].cancel()
            
        # Start a new timer for debounce
        timer = threading.Timer(self.debounce_seconds, self._sync_file, args=[event.src_path])
        self.timers[event.src_path] = timer
        timer.start()
        
    def _sync_file(self, file_path):
        print(f"Reverse Sync triggered for edited file: {file_path}")
        try:
            decompiler.sync_file(file_path)
        except Exception as e:
            print(f"Error syncing {file_path}: {e}")

def start_watcher(directory_path="repo_out"):
    if not os.path.exists(directory_path):
        os.makedirs(directory_path, exist_ok=True)
        
    event_handler = TraceFileHandler()
    observer = Observer()
    observer.schedule(event_handler, path=directory_path, recursive=True)
    
    # We run the observer as a daemon thread so it doesn't block the main event loop
    observer_thread = threading.Thread(target=observer.start, daemon=True)
    observer_thread.start()
    print(f"Bi-Directional Watcher started on {directory_path} with 5s debounce...")
    return observer
