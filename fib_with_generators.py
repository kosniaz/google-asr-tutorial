import time

def fib_gen():
    yield 1
    yield 1
    a=1
    b=1
    while True:
        time.sleep(0.2)
        yield b+a
        tmp = a
        a=b
        b=tmp+b
    
for i in fib_gen():
    print(i)