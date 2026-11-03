"""Decode a synthetic local clip with bundled VLC; no device output or user config."""
import ctypes as C,json,os,pathlib,sys,time
r=pathlib.Path(sys.argv[1]);fixture=pathlib.Path(sys.argv[2]);handle=os.add_dll_directory(str(r/'vlc'));os.environ['VLC_PLUGIN_PATH']=str(r/'vlc/plugins')
lib=C.CDLL(str(r/'vlc/libvlc.dll'))
def api(name,result,args):
 fn=getattr(lib,name);fn.restype=result;fn.argtypes=args;return fn
ptr=C.c_void_p
new=api('libvlc_new',ptr,[C.c_int,C.POINTER(C.c_char_p)]);release=api('libvlc_release',None,[ptr]);media_new=api('libvlc_media_new_path',ptr,[ptr,C.c_char_p]);media_release=api('libvlc_media_release',None,[ptr]);player_new=api('libvlc_media_player_new_from_media',ptr,[ptr]);player_release=api('libvlc_media_player_release',None,[ptr]);play=api('libvlc_media_player_play',C.c_int,[ptr]);state=api('libvlc_media_player_get_state',C.c_int,[ptr]);stop=api('libvlc_media_player_stop',None,[ptr])
class Stats(C.Structure):
 _fields_=[('read_bytes',C.c_int),('input_bitrate',C.c_float),('demux_read_bytes',C.c_int),('demux_bitrate',C.c_float),('demux_corrupted',C.c_int),('demux_discontinuity',C.c_int),('decoded_video',C.c_int),('decoded_audio',C.c_int),('displayed_pictures',C.c_int),('lost_pictures',C.c_int),('played_abuffers',C.c_int),('lost_abuffers',C.c_int),('sent_packets',C.c_int),('sent_bytes',C.c_int),('send_bitrate',C.c_float)]
getstats=api('libvlc_media_get_stats',C.c_int,[ptr,C.POINTER(Stats)])
args=[b'--ignore-config',b'--no-media-library',b'--vout=dummy',b'--no-audio',b'--no-video-title-show'];vector=(C.c_char_p*len(args))(*args);print('before-new',flush=True);instance=new(len(args),vector);print('after-new',flush=True)
if not instance:raise RuntimeError('libvlc_new failed')
media=media_new(instance,os.fsencode(str(fixture)));print('after-media',flush=True);player=player_new(media);print('after-player',flush=True)
try:
 print('before-play',flush=True);assert play(player)==0;print('after-play',flush=True)
 deadline=time.monotonic()+15;states=[];decoded=0
 while time.monotonic()<deadline:
  current=state(player);states.append(current);stats=Stats();getstats(media,C.byref(stats));decoded=max(decoded,stats.decoded_video)
  if current in (6,7):break
  time.sleep(.05)
 if states[-1]!=6 or decoded<1:raise RuntimeError(f'Playback did not decode to ended: {states}, frames={decoded}')
 print(json.dumps({'ended':True,'decoded_video':decoded,'states':sorted(set(states)),'fixture':str(fixture)}))
finally:stop(player);player_release(player);media_release(media);release(instance)
