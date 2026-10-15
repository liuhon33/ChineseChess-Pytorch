with open(r'e:\cc\ChineseChess-AlphaZero\cchess_alphazero\agent\player.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = []
for i, line in enumerate(lines):
    if 111 <= i <= 124:
        continue
    if i == 110:
        new_lines.append(line)
        new_lines.append('        limit = 256                 # max prediction queue size\n')
        new_lines.append('        while not self.job_done:\n')
        new_lines.append('            self.run_lock.acquire()\n')
        new_lines.append('            t_data = None\n')
        new_lines.append('            with self.q_lock:\n')
        new_lines.append('                l = min(limit, len(self.buffer_history))\n')
        new_lines.append('                if l > 0:\n')
        new_lines.append('                    t_data = self.buffer_planes[0:l]\n')
        new_lines.append('            if t_data is not None:\n')
        new_lines.append('                # logger.debug(f"send queue size = {l}")\n')
        new_lines.append('                self.pipe.send(t_data)\n')
        new_lines.append('            else:\n')
        new_lines.append('                self.run_lock.release()\n')
        new_lines.append('                # Producers need q_lock to enqueue work. Sleeping with it held\n')
        new_lines.append('                # can starve every search thread on Linux for minutes.\n')
        new_lines.append('                sleep(0.001)\n')
    else:
        new_lines.append(line)

with open(r'e:\cc\ChineseChess-AlphaZero\cchess_alphazero\agent\player.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)
