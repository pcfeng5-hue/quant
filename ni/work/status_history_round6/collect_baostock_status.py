"""Read-only public BaoStock anonymous protocol; no personal account or key."""
import pathlib, sys, socket, json, datetime, hashlib, traceback
OUT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0,str(OUT/'sdk'))
import baostock as bs
import baostock.util.socketutil as su
import baostock.common.context as ctx

socket.setdefaulttimeout(20)
metadata=[]
original_send=su.send_msg
original_connect=su.SocketUtil.connect
class CaptureSocket:
    def __init__(self, sock): self.sock=sock; self.received=[]
    def send(self,data): return self.sock.send(data)
    def recv(self,n):
        value=self.sock.recv(n)
        self.received.append(value)
        if not value: raise ConnectionError('Server closed stream before complete frame')
        return value
    def close(self): return self.sock.close()
def connect(self,key):
    original_connect(self,key)
    setattr(ctx,'default_socket',CaptureSocket(getattr(ctx,'default_socket')))
def send(msg):
    stamp=datetime.datetime.now(datetime.timezone.utc).isoformat()
    sock=getattr(ctx,'default_socket',None)
    if sock: sock.received=[]
    result=original_send(msg)
    raw=b''.join(sock.received) if sock else b''
    row={'retrieved_at':stamp,'request_method':msg.split('\x01')[4] if len(msg.split('\x01'))>4 else 'unknown',
         'public_anonymous_protocol':True,'request_utf8':msg,'received_bytes':len(raw)}
    if raw:
        sha=hashlib.sha256(raw).hexdigest();p=OUT/f'baostock_wire_{len(metadata)+1}_{sha[:16]}.bin';p.write_bytes(raw)
        row.update(sha256=sha,raw_path=str(p))
    if result is not None:
        decoded=result.encode();sha=hashlib.sha256(decoded).hexdigest();p=OUT/f'baostock_decoded_{len(metadata)+1}_{sha[:16]}.txt';p.write_bytes(decoded)
        row.update(decoded_sha256=sha,decoded_path=str(p))
    else: row['error']='SDK returned no decoded response; see captured stdout/stderr'
    metadata.append(row);(OUT/'baostock_protocol_requests.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2))
    return result
su.SocketUtil.connect=connect
su.send_msg=send
output={'source':'BaoStock public anonymous API','server':'public-api.baostock.com:10030',
        'scope':{'code':'sz.002414','start_date':'2023-01-01','end_date':'2026-10-15'},
        'sdk_version':'0.9.4','personal_account_used':False,'historical_input_eligible':False}
try:
    login=bs.login()
    output['anonymous_handshake']={'error_code':login.error_code,'error_msg':login.error_msg}
    if login.error_code=='0':
        fields='date,code,open,high,low,close,preclose,volume,amount,adjustflag,turn,tradestatus,pctChg,isST'
        result=bs.query_history_k_data_plus('sz.002414',fields,start_date='2023-01-01',end_date='2026-10-15',frequency='d',adjustflag='3')
        output['query']={'fields':fields,'frequency':'d','adjustflag':'3','error_code':result.error_code,'error_msg':result.error_msg}
        rows=[]
        while result.error_code=='0' and result.next(): rows.append(dict(zip(result.fields,result.get_row_data())))
        output['rows']=rows
        output['fields']=result.fields
        output['row_count']=len(rows)
        logout=bs.logout();output['logout']={'error_code':logout.error_code,'error_msg':logout.error_msg}
except Exception as e:
    output['error']=repr(e);output['traceback']=traceback.format_exc()
(OUT/'baostock_daily_status.json').write_text(json.dumps(output,ensure_ascii=False,indent=2))
print(json.dumps({k:v for k,v in output.items() if k not in ('rows','traceback')},ensure_ascii=False))
