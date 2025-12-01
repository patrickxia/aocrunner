#!/usr/bin/env python3

YEAR=2025
DAY=1

import datetime
import inotify.adapters
import select
import sys
import sty
import termios
import tty
import threading
from subprocess import Popen, PIPE, TimeoutExpired
from aocd import AocdError
from aocd.models import Puzzle

old_settings = termios.tcgetattr(sys.stdin.fileno())
tty.setcbreak(sys.stdin.fileno())

def isData():
    return select.select([sys.stdin], [], [], 0) == ([sys.stdin], [], [])


def communicate_thread(data, data_out, evt_done):
    proc = Popen(["/bin/bash", "-c", " ".join(sys.argv[1:])], stdin=PIPE, stdout=PIPE, stderr=PIPE)
    def get_results():
        stdout, stderr = proc.communicate(input=bytes(data, 'utf-8'))
        data_out[0] = stdout
        data_out[1] = stderr
        data_out[2] = proc.returncode
        evt_done.set()
    return get_results, proc

def print_results(out, err, type):
    stdouts = out.decode("utf-8").strip().split("\n")
    stderrs = err.decode("utf-8").strip().split("\n")
    for lines, fd in ((stdouts, "out"), (stderrs, "err")):
        if lines and lines != [''] and (type != 'out' and len(lines) > 1):
            print(sty.fg(200,200,200), end='')
            print(f'******* {type} {fd} ******* ')
            for line in lines:
                print(line)
            print(sty.fg.rs, end='')
    ans = stdouts[-1]
    return ans

puzzle = Puzzle(year=YEAR, day=DAY)
sample_data = None
expected_sample = None
a_is_done = puzzle.answered_a

if len(puzzle.examples) > 0:
    sample_data = puzzle.examples[0].input_data
    if not a_is_done:
        expected_sample = puzzle.examples[0].answer_a
    else:
        expected_sample = puzzle.examples[0].answer_b
input_data = puzzle.input_data
done = False

i = inotify.adapters.Inotify()
i.add_watch('.')

while not done:
    print(f"[{datetime.datetime.now()}] running...")
    if sample_data:
        example_results = [None, None, None]
        example_done = threading.Event()
        example_cancel = threading.Event()
        example_worker, example_proc = communicate_thread(sample_data, example_results, example_done)
        example_thread = threading.Thread(target=example_worker)
        example_thread.start()

    input_results = [None, None, None]
    input_done = threading.Event()
    input_cancel = threading.Event()
    input_worker, input_proc = communicate_thread(input_data, input_results, input_done)
    input_thread = threading.Thread(target=input_worker)
    input_thread.start()

    repeat = False
    while not (input_done.wait(0.05)):
        for event in i.event_gen(yield_nones=False, timeout_s=0.01):
            (q, type_names, path, filename) = event
            if 'IN_CLOSE_WRITE' not in type_names:
                continue
            if not repeat:
                print('Files changed -- killing all')
                if sample_data: example_proc.kill()
                input_proc.kill()
                repeat = True
    if repeat: continue

    if sample_data:
        example_done = example_done.wait(0.05)
        if example_done:
            sample_ans = print_results(example_results[0], example_results[1], 'sample')
        else:
            sample_ans = "TIMEOUT"
            example_proc.kill()

    input_ans = print_results(input_results[0], input_results[1], 'input')

    if sample_data:
        print(f'Sample process exit {"" if example_results[2] == 0 else example_results[2]}: result {sample_ans}, expected part {"b" if a_is_done else "a"} {expected_sample}')
        if sample_ans == expected_sample:
            print(f'🔥 🔥 🔥  🚀🚀🚀 sample ok')
        elif expected_sample is not None and len(expected_sample) > 0 and all(x.isdigit() for x in sample_ans) and all(x.isdigit() for x in expected_sample):
            print(f'sample NOT ok ❌ ')
    print(f'Input process exit {"" if input_results[2] == 0 else input_results[2]}: result {input_ans}')

    while isData():
        _ = sys.stdin.read(1)
    hanging_line = False
    if not a_is_done:
        print(f"Submit {input_ans} for Part A? ", flush=True, end='')
        hanging_line = True
    else:
        print(f"Submit {input_ans} for Part B? ", flush=True, end='')
        hanging_line = True


    wait_for_file = True
    while not done and wait_for_file:
        while isData():
            c = sys.stdin.read(1)
            if c == 'q' or c == '\x1b':
                print('Received quit signal')
                done = True
                break
            if c == 's':
                print_results(example_results[0], example_results[1], 'sample')
            if c == 'y':
                print()
                print(f'Submitting {input_ans}...', flush=True)
                try:
                    if not a_is_done:
                        puzzle.answer_a = input_ans
                        a_is_done = puzzle.answered_a
                        if a_is_done:
                            if input_ans != puzzle.answer_a:
                                # out-of-sync with reality
                                puzzle.answer_b = input_ans
                            if len(puzzle.examples) > 0:
                                expected_sample = puzzle.examples[0].answer_b
                    else:
                        puzzle.answer_b = input_ans
                    print("Done")
                except AocdError as e:
                    print(f'Error: {e}')
        if done:
            break

        for event in i.event_gen(yield_nones=False, timeout_s=0.01):
            (q, type_names, path, filename) = event
            if 'IN_CLOSE_WRITE' not in type_names:
                continue
            wait_for_file = False
        if not wait_for_file:
            print("... Aborting -- files changed")

termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)
