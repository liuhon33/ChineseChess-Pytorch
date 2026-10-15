# Evaluation Deadlock (Gridlock) Fix - October 2026

## The Problem
During evaluation (`run.py eval`), the AI typically takes around 0.1s to make a move. However, under certain conditions—particularly when evaluating the new generation against the best model—the evaluation speed would spontaneously plummet to hundreds of seconds per move, causing severe stalls and seemingly hanging the process.

This problem did not occur during `self_play` mode.

## Root Cause Analysis
The issue was a classic circular deadlock (gridlock) caused by a lock (`self.q_lock`) being held across an Inter-Process Communication (IPC) blocking operation, specifically when the system was under heavy multiprocessing load.

### Architecture Overview
The system uses multiple threads and processes:
1. **MCTS Threads**: In `expand_and_evaluate()`, these threads acquire `q_lock` to enqueue game states into `buffer_planes`.
2. **Sender Thread**: In `sender()`, this thread acquired `q_lock`, read the `buffer_planes`, and then called `self.pipe.send(t_data)` to send the states to the central API worker.
3. **API Worker (`api.py`)**: A separate process that polls incoming pipes from all players, runs the neural network batch, and sends the results back via `result_pipe.send(rets)`.
4. **Receiver Thread**: In `receiver()`, this thread polled `self.pipe.recv()` and then acquired `q_lock` to update the tree and clean up `buffer_planes`.

### How the Deadlock Triggered
In `eval` mode, two player processes (Red and Black) share the same API worker process to evaluate moves.
1. The API worker becomes a bottleneck under heavy evaluation load because it is serving two models simultaneously.
2. Because the API worker is busy, the OS pipe buffer for `self.pipe.send(t_data)` fills up.
3. Once the pipe buffer is full, `self.pipe.send(t_data)` blocks until the API worker reads from it.
4. **The Flaw:** `self.pipe.send(t_data)` was being called *inside* the `with self.q_lock:` block in the `sender()` thread. This meant the `sender` thread was blocked indefinitely while holding `q_lock`.

### The Circular Wait
With `q_lock` held by the blocked `sender` thread:
1. MCTS threads could no longer enqueue jobs.
2. The `receiver` thread could poll and read `self.pipe.recv()`, but it could not process them because it immediately waited on `with self.q_lock:`. 
3. Because the `receiver` thread was blocked waiting for `q_lock`, it stopped draining the return pipe.
4. With the return pipe no longer being drained, the API worker's `result_pipe.send(rets)` operation blocked when its outgoing OS buffer filled up.
5. Because the API worker was blocked sending results, it stopped reading from the incoming pipes.
6. Because the API worker stopped reading from the incoming pipes, the `sender`'s pipe buffer remained full.
7. Thus, the `sender` remained blocked, forever holding `q_lock`.

**Gridlock was achieved.** The system would sit idle until timeouts eventually cleared the buffers, resulting in moves taking 60 to 150 seconds.

## The Fix
The solution was to perform the blocking IPC operation *outside* the critical section. 

In `cchess_alphazero/agent/player.py` (`sender()`):

### Before:
```python
with self.q_lock:
    if l == 0:
        self.run_lock.release()
        sleep(0.001)
        continue

    t_data = self.buffer_planes[0:l]
    self.pipe.send(t_data)
    # ...
```

### After:
```python
t_data = None
with self.q_lock:
    if l == 0:
        self.run_lock.release()
        sleep(0.001)
        continue

    t_data = self.buffer_planes[0:l]
    # Do not call self.pipe.send() inside the lock!

if t_data is not None:
    self.pipe.send(t_data)
    # ...
```

By releasing `q_lock` before calling `self.pipe.send(t_data)`, the lock remains available. If the sender's pipe fills up and `self.pipe.send()` blocks, the `receiver` thread can still acquire `q_lock`, drain the return pipe, unblock the API worker, which then unblocks the sender. The circular wait is broken.

## Validation
1. **Local tests:** Ran `pytest cchess_alphazero/tests/test_self_play_sender.py` locally to ensure the change didn't break core logic.
2. **Remote test:** Transferred the patched `player.py` to the remote Torch cluster and ran an evaluation:
   ```bash
   module load StdEnv/2023 python/3.12
   source ~/venvs/torch210_cu128/bin/activate
   python cchess_alphazero/run.py eval --data-dir testdata
   ```
   **Result:** Evaluation of full games (80-90 turns) completed in ~4.9 seconds instead of hanging for hundreds of seconds, verifying the gridlock is completely resolved.
