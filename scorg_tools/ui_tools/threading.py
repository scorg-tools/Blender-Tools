import threading
import concurrent.futures
import multiprocessing
import time
import queue

class ThreadManager:
    """
    A simple thread manager for running tasks in background threads.
    Supports pausing, resuming, and cancelling tasks.
    """
    
    def __init__(self, max_workers=None):
        """
        Initialize the ThreadManager.
        
        Args:
            max_workers (int, optional): Number of worker threads. 
                                         Defaults to number of CPU cores.
        """
        if max_workers is None:
            try:
                max_workers = multiprocessing.cpu_count()
            except NotImplementedError:
                max_workers = 4
                
        self.max_workers = max_workers
        self.executor = None
        self.futures = []
        self.is_paused = False
        self.pause_condition = threading.Condition()
        self._shutdown = False

    def start(self):
        """Start the thread pool executor."""
        if self.executor is None:
            self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers)
            self._shutdown = False

    def stop(self, wait=True):
        """
        Stop the thread manager and shutdown the executor.
        
        Args:
            wait (bool): If True, wait for pending futures to complete.
        """
        self._shutdown = True
        self.cancel_all()
        if self.executor:
            self.executor.shutdown(wait=wait)
            self.executor = None

    def pause(self):
        """Pause execution of new tasks."""
        self.is_paused = True

    def resume(self):
        """Resume execution of tasks."""
        with self.pause_condition:
            self.is_paused = False
            self.pause_condition.notify_all()

    def cancel_all(self):
        """Cancel all pending futures."""
        for future in self.futures:
            if not future.done():
                future.cancel()
        self.futures = [f for f in self.futures if not f.done()]

    def submit(self, fn, *args, **kwargs):
        """
        Submit a task to be executed.
        
        Args:
            fn (callable): The function to execute.
            *args: Arguments for the function.
            **kwargs: Keyword arguments for the function.
            
        Returns:
            concurrent.futures.Future: The future object representing the task.
        """
        if self.executor is None:
            self.start()

        def wrapped_fn(*args, **kwargs):
            # Check for pause
            with self.pause_condition:
                while self.is_paused and not self._shutdown:
                    self.pause_condition.wait()
            
            if self._shutdown:
                return None
                
            return fn(*args, **kwargs)

        future = self.executor.submit(wrapped_fn, *args, **kwargs)
        self.futures.append(future)
        
        # Clean up finished futures periodically
        self.futures = [f for f in self.futures if not f.done()]
        
        return future

    def process_batch(self, func, items, progress_callback=None):
        """
        Process a batch of items using the thread pool.
        
        Args:
            func (callable): The function to execute for each item. 
                             Should accept a single argument (the item).
            items (list): List of items to process.
            progress_callback (callable, optional): Callback function to report progress.
                                                    Signature: callback(current, total)
                                                    
        Returns:
            list: List of futures representing the tasks.
        """
        if self.executor is None:
            self.start()
            
        futures = []
        total = len(items)
        completed_count = 0
        lock = threading.Lock()
        
        def done_callback(future):
            nonlocal completed_count
            with lock:
                completed_count += 1
                current = completed_count
                
            if progress_callback:
                try:
                    progress_callback(current, total)
                except Exception as e:
                    print(f"Error in progress callback: {e}")

        for item in items:
            future = self.submit(func, item)
            future.add_done_callback(done_callback)
            futures.append(future)
            
        return futures

    def shutdown(self):
        """Alias for stop."""
        self.stop()
