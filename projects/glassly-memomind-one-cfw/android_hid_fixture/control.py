#!/usr/bin/env python3
"""Interactive JSON-lines controller; never starts BLE or injects a report itself."""
import argparse,json,socket,sys,threading

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--port',type=int,default=38742)
    p.add_argument('--token-file',required=True)
    a=p.parse_args()
    with open(a.token_file,encoding='utf-8') as f: token=f.read().strip()
    if not 32<=len(token)<=128: p.error('token must be32..128 characters')
    with socket.create_connection(('127.0.0.1',a.port),timeout=5) as sock:
        wire=sock.makefile('rb');sock.sendall((json.dumps({'op':'hello','id':'hello','token':token})+'\n').encode())
        first=wire.readline(65537)
        if not first or len(first)>65536: raise RuntimeError('missing/oversized handshake')
        result=json.loads(first)
        if result.get('id')!='hello' or result.get('ok') is not True: raise RuntimeError('authentication failed')
        print(first.decode().rstrip(),flush=True);sock.settimeout(None)
        finished=threading.Event()
        def receive():
            try:
                while True:
                    line=wire.readline(65537)
                    if not line:break
                    if len(line)>65536:raise RuntimeError('oversized fixture message')
                    json.loads(line);print(line.decode().rstrip(),flush=True)
            except (OSError,ValueError,RuntimeError) as e:print(str(e),file=sys.stderr)
            finally:finished.set()
        t=threading.Thread(target=receive,daemon=True);t.start()
        print('Enter one JSON request per line. Keep stdin open; EOF closes the fixture. No automatic start/report/release.',file=sys.stderr)
        try:
            for seq,line in enumerate(sys.stdin,1):
                if finished.is_set():break
                try:
                    if len(line.encode())>4096:raise ValueError('request too long')
                    q=json.loads(line)
                    if not isinstance(q,dict) or q.get('op') not in {'status','start','stop','report','release'}:raise ValueError('invalid operation')
                    q.setdefault('id',seq);sock.sendall((json.dumps(q,separators=(',',':'))+'\n').encode())
                except (ValueError,OSError) as e:print(str(e),file=sys.stderr)
        except KeyboardInterrupt:pass
        finally:
            try:sock.shutdown(socket.SHUT_RDWR)
            except OSError:pass
            t.join(timeout=2)
if __name__=='__main__':main()
