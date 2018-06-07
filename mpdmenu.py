#!/usr/bin/env python3

from subprocess import run, PIPE, DEVNULL
from mpd import *
from sys import argv, stdout, stderr
from getopt import gnu_getopt, GetoptError
import re

def usage():
    print(
'''
usage: mpdmenu [options] [dmenu_cmd]

        dmenu_cmd
            command line to execute on new state (defaults to "dmenu")

    Options
        -a ADDRESS, --address=ADDRESS
            Address used to connect to mpd (defaults to 'localhost')

        -p PORT, --port=PORT
            Port used to connect to mpd. Must be a number (defaults to 6600)

        -t TIMEOUT, --timeout
            Timeout of connection. Must be a number (defaults to 60)
'''
, file=stderr)

dmenu_cmd = 'dmenu'

def esc_pressed(r):
    return r == None

def none_selected(r):
    return len(r) == 0

def sformat_track(index, track):
    if 'artist' in track:
        return '{} {} - {}'.format(index, track['artist'], track['title'])
    elif 'title' in track:
        return '{} {}'.format(index, track['title'])
    else:
        return '{} {}'.format(index, track['file'])

def dmenu(input, prompt='', custominput=False):
    p = run(
            dmenu_cmd + ' -p "{}"'.format(prompt), 
            shell=True, 
            input='\n'.join(input), 
            universal_newlines=True, 
            stdout=PIPE
        )
    if p.returncode != 0:
        return None
    output = p.stdout.strip('\n')
    items = re.split('\n+', output)
    if not custominput:
        for item in items:
            if item not in input:
                items.remove(item)
    return items

def dmenu_select_tracks(tracks, prompt='""', usepos=False):
    t = tracks
    if usepos:
        tracks_fmt = [sformat_track(t[i]['pos'], t[i]) for i in range(0,len(t))]
    else:
        tracks_fmt = [sformat_track(i, t[i]) for i in range(0,len(t))]
    r =  dmenu(tracks_fmt, prompt=prompt)
    if esc_pressed(r) or none_selected(r):
        return None
    selected_tracks = r
    indices = [int(st.split(' ', 1)[0]) for st in selected_tracks]
    if usepos:
        selected_tracks = list(filter(lambda t: int(t['pos']) in indices, tracks))
    else:
        selected_tracks = [tracks[i] for i in indices]
    return selected_tracks



def mpd_resume(client, command):
    client.play()
    # client.pause(0)

def mpd_pause(client, command):
    client.pause(1)

def mpd_stop(client, command):
    client.stop()

def mpd_toggle(client, command):
    state = client.status()['state']
    if state == 'play':
        client.pause(1)
    else:
        client.play()
        #client.pause(0)
    
def mpd_current(client, command):
    current = client.currentsong()
    dmenu_select_tracks([current], prompt='Current:', usepos=True)

def mpd_previous(client, command):
    client.previous()

def mpd_next(client, command):
    client.next()

def mpd_clear(client, command):
    client.clear()


def build_query(client, query):
    tags = client.tagtypes()
    while True:
        r = dmenu(tags, prompt='Type:')
        if esc_pressed(r):
            break
        if none_selected(r):
            continue
        qtype = r[0].lower()
        r = dmenu(
                client.list(qtype, *query), 
                prompt=qtype.capitalize()+':'
            )
        if esc_pressed(r) or none_selected(r):
            continue
        item = r[0]
        query.append(qtype)
        query.append(item)

    return query

LOOP_END = 0
LOOP_CONT = 1

def search_add(client, query):
    client.searchadd(*query)
    return LOOP_END

def search_list(client, query):
    s = client.search(*query)
    tracks = ['{} {} - {}'.format(i, s[i]['artist'], s[i]['title']) for i in range(0,len(s))]
    dmenu(tracks, prompt='Selected:')
    return LOOP_CONT

def search_select(client, query):
    s = client.search(*query)
    tracks = dmenu_select_tracks(s, 'Selected:')
    if esc_pressed(tracks):
        return LOOP_CONT
    for track in tracks:
        client.add(track['file'])
    return LOOP_END

def search_play(client, query):
    client.clear()
    return search_add(client, query)

search_actions = { 
    'add tags'       : build_query,
    'add'            : search_add,
    'list'           : search_list,
    'select and add' : search_select,
    'play'           : search_play
}

def mpd_search(client, command):
    query = build_query(client, [])
    if query == None or len(query) == 0:
        return None
    while True:
        r = dmenu(search_actions)
        if esc_pressed(r) or none_selected(r):
            return None
        action = r[0].lower()
        lc = search_actions[action](client,query)
        if lc == LOOP_END:
            break

def mpd_play(client, command):
    current = client.currentsong()
    playlist = client.playlistinfo()
    if current:
        playlist.remove(current)
        playlist.insert(0, current)
    tracks = dmenu_select_tracks(playlist, prompt='Play:', usepos=True)
    if tracks == None:
        return
    client.play(tracks[0]['pos'])

playlist_actions = ['play', 'delete', 'crop']
def mpd_playlist(client, command):
    current = client.currentsong()
    playlist = client.playlistinfo()
    playlist.remove(current)
    playlist.insert(0, current)
    tracks = dmenu_select_tracks(playlist, prompt='Playlist:', usepos=True)

    if tracks == None:
        return
    r = dmenu(playlist_actions, prompt='Action:')
    if esc_pressed(r) or none_selected(r):
        return
    action = r[0].lower()
    if action not in playlist_actions:
        return
    if action == 'play':
        client.play(tracks[0]['pos'])
    elif action == 'delete':
        indices = sorted([int(t['pos']) for t in tracks])
        adj = 0
        for i in indices:
            client.delete(i-adj)
            adj+=1
    elif action == 'crop':
        adj = 0
        for track in playlist:
            if track not in tracks:
                client.delete(int(track['pos'])-adj)
                adj = adj + 1
    print(tracks)
    return

def mpd_playopt(client, command):
    status = client.status()[command]
    if command in ['repeat', 'random', 'single', 'consume']:
        sel = ['On', 'Off']
        if status == '1':
            sel.reverse()
        r = dmenu(sel, prompt=command.capitalize())
        if esc_pressed(r) or none_selected(r):
            return
        val = int(r[0].strip() == 'On')
        if command == 'repeat':
            client.repeat(val)
        elif command == 'random':
            client.random(val)
        elif command == 'single':
            client.single(val)
        else:
            client.consume(val)
    if command == 'volume':
        r = dmenu([status], prompt="Volume: ", custominput=True)
        if esc_pressed(r) or none_selected(r):
            return
        s = r[0].strip()
        val = int(s.strip('+- %\n\t'))
        prevvol = int(status)
        if s[0]=='-':
            client.setvol(max(0,prevvol-val))
        elif s[0]=='+':
            client.setvol(min(100,prevvol+val))
        else:
            client.setvol(max(0,min(100,val)))
            
commands = {
    'resume'    : mpd_resume,
    'pause'     : mpd_pause,
    'stop'      : mpd_stop,
    'toggle'    : mpd_toggle,
    'current'   : mpd_current,
    'previous'  : mpd_previous,
    'next'      : mpd_next,
    'clear'     : mpd_clear,
    'search'    : mpd_search,
    'play'      : mpd_play,
    'playlist'  : mpd_playlist,
    'repeat'    : mpd_playopt,
    'random'    : mpd_playopt,
    'single'    : mpd_playopt,
    'consume'   : mpd_playopt,
    'volume'    : mpd_playopt,
    # 'options'   : mpd_options
}

def main(address='localhost', port=6600, timeout=60):
    client = MPDClient();
    client.timeout = timeout;
    client.connect(address, port)

    while True:
        r = dmenu(commands.keys(), prompt='Action: ')
        if esc_pressed(r):
            return 
        if none_selected(r):
            continue
        command = r[0]
        if command not in commands:
            break
        commands[command](client, command.lower())

    client.close()
    client.disconnect()




if __name__=='__main__':
    address = 'localhost'
    port = 6600
    timeout = 60
    try:
        opts, args = gnu_getopt(argv[1:], 'a:p:t:', ['--address=', '--port=', '--timeout'])
        for opt in opts:
            key = opt[0]
            value = opt[1]
            if key in ['-a', '--address']:
                address=value
            elif key in ['-p', '--port']:
                port=int(value)
            elif key in ['-t', '--timeout']:
                timeout=int(value)
            else:
                usage()
                exit(1)
    except (ValueError, GetoptError):
        usage()
        exit(1)

    if len(args) != 0:
        dmenu_cmd = ' '.join(args)
    else:
        rc = run('which dmenu', shell=True, stdout=DEVNULL).returncode 
        if rc != 0:
            print('"which dmenu" returned {}'.format(rc), file=stderr)
            exit(1);
    main(address=address, port=port, timeout=timeout) 
