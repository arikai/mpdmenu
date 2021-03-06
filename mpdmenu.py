#!/usr/bin/env python3

'''
    mpdmenu - mpd client powered by dmenu and python-mpd2

    Copyright 2018 Yaroslav Rogov

    Licensed under the Apache License, Version 2.0 (the "License");
    you may not use this file except in compliance with the License.
    You may obtain a copy of the License at

        http://www.apache.org/licenses/LICENSE-2.0

    Unless required by applicable law or agreed to in writing, software
    distributed under the License is distributed on an "AS IS" BASIS,
    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
    See the License for the specific language governing permissions and
    limitations under the License.
'''
from subprocess import Popen, PIPE, DEVNULL
from mpd import MPDClient
from mpd.base import CommandError, ConnectionError
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
''', file=stderr)

dmenu_cmd = 'dmenu'

def esc_pressed(r):
    return r == None

def none_selected(r):
    return type(r) is list and len(r) == 0

def sformat_track(index, track):
    a = ['{} '.format(index)]
    if 'artist' in track:
        a.append('{} - '.format(track['artist']))
    if 'title' in track:
        a.append(track['title'])
    else:
        a.append(track['file'])
    return ''.join(a)

def dmenu(input, prompt='', custominput=False):
    p = Popen(
            dmenu_cmd + (' -p "{}"'.format(prompt) if prompt else ''),
            shell=True,
            stdin=PIPE,
            universal_newlines=True,
            stdout=PIPE
        )
    p.stdin.write('\n'.join(input))
    p.stdin.close()
    p.wait()
    if p.returncode != 0:
        return None
    items = [ s[:-1] for s in p.stdout.readlines()]
    if not custominput:
        for item in items:
            if item not in input:
                items.remove(item)
    return items

def dmenu_select_tracks(tracks, prompt='""', usepos=False, ranges=True):
    t = tracks
    if usepos:
        tracks_fmt = [sformat_track(t[i]['pos'], t[i]) for i in range(0,len(t))]
    else:
        tracks_fmt = [sformat_track(i, t[i]) for i in range(0,len(t))]

    stype = 'set'
    while True:
        r = dmenu(tracks_fmt, prompt=prompt)
        if esc_pressed(r) or none_selected(r):
            return None
        selected_tracks = r
        indices = [int(st.split(' ', 1)[0]) for st in selected_tracks]
        if not ranges or len(indices)==1:
            break
        r = dmenu(['set', 'ranges'], prompt='Selection')
        if esc_pressed(r):
            continue
        if none_selected(r):
            stype = 'set'
        else:
            stype = r[0]
        break

    # Ranges are inclusive on both ends
    if stype == 'ranges':
        selected_tracks = []
        ranges = []
        if len(indices) % 2 == 1:
            indices.append(indices[-1])
        pairs = [indices[i:i+2] for i in range(0,len(indices),2)]
        for a,b in pairs:
            if a > b:
                t=a; a=b; b=t;
            found = False
            for i in range(0,len(ranges)):
                ra, rb = ranges[i]
                if ra < a < rb:
                    ranges[i][1] = b
                elif ra < b < rb:
                    ranges[i][0] = a
                elif a < ra and rb < b:
                    ranges[i][0] = a
                    ranges[i][1] = b
                elif rb < a:
                    ranges.insert(i+1,[a,b])
                else:
                    continue
                found = True
                break
            if not found:
                ranges.append([a,b])
        if usepos:
            track_at_pos = dict((int(t['pos']), t) for t in tracks)
        else:
            track_at_pos = dict((i, tracks[i]) for i in range(0, len(t)))
        for a,b in ranges:
            selected_tracks.extend([track_at_pos[i] for i in range(a,b+1)])
    else:
        selected_tracks=[]
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

def mpd_previous(client, command):
    client.previous()

def mpd_next(client, command):
    client.next()

def mpd_clear(client, command):
    client.clear()


"""Interactively build immediate representation of query to MPD via dmenu (see execute_query)

:param client: client-connection to MPD
:type client: MPDClient
:param command: command that caused a call to this function.
                Used to specialize behaviour of interactive query builder.
                Currently possible values: 'find', 'search'
:type command: str
:param query: previously built (using this function) query immediate representation.
              Passed to reenter function.
              Format: [type_str, key_str or [key_str1, key_str2, ... ], ...]
              (default is [])
:type query: list
"""
def build_query(client, command, query=[]):
    tags = ['Any']
    tags += client.tagtypes()

# BUG: if you delete this lines, find (or search) and play something, then find 
# again, query will be the same from the previous 'find'
    if not query:
        query = []

    while True:
        r = dmenu(tags, prompt='Type')
        if esc_pressed(r):
            break
        if none_selected(r):
            continue
        qtype = r[0].lower()
        if qtype == 'any':
            r = dmenu([], prompt='Any tag', custominput=True)
        else:
            if len(query) == 0:
                values = client.list(qtype)
            else:
                values = execute_query(client, query, client.list, args=[qtype])
                values = sorted(set(values))
            r = dmenu(values, prompt='{}'.format(qtype.capitalize()), custominput = (command == 'search'))
        if esc_pressed(r) or none_selected(r):
            continue
        if len(r) > 1:
            item = r
        else:
            item = r[0]
        query.append(qtype)
        query.append(item)

    return query

"""Construct query to MPD from immediate representation
:param client: client-connection to MPD
:type client: MPDClient
:param query: previously built (using this function) query immediate representation.
              Format: [type_str, key_str or [key_str1, key_str2, ... ], ...]
:type query: list
:param function: client.function which will be used for this query.
              Possible values are: client.searchadd, client.list, etc.
              I.e. any command that works with query
:type function: function of MPDClient that works with query
:param args: TODO I can't remember why this param is so ugly and why array
:type args: array
"""
def execute_query(client, query, function, args=None):
    queries = []
    pairs = [query[i:i+2] for i in range(0,len(query),2)]
    if len(pairs) > 0:
        qtype, value = pairs[0]
        pairs = pairs[1:]
        if type(value) is list:
            for v in value:
                queries.append([qtype,v])
        else:
            queries.append([qtype,value])
        for qtype, value in pairs:
            if type(value) is list:
                new_queries = []
                for query in queries:
                    new_queries += [query + [qtype, v] for v in value]
                queries = new_queries
            else:
                for query in queries:
                    query.append(qtype)
                    query.append(value)

    results = []
    if args:
        main_function = function
        function = lambda *query: main_function(*args, *query)
    for query in queries:
        result = function(*query)
        if result != None:
            results += result
    return results;

def prompt_save_playlist(client):
    cur_len = int(client.status()['playlistlength'])
    if cur_len > 0:
        save_playlist(client, prompt='Save playlist?')


# If tracks are None, current playlist is saved
def save_playlist(client, prompt='Playlist name', tracks=None):
    while True:
        r = dmenu([], prompt=prompt, custominput=True)
        # Saved if not zero-length name typed, not otherwise
        if esc_pressed(r) or r[0]=='':
            break
        name = r[0]
        try:
            client.save(name)
        except CommandError:
            r = dmenu(['Yes', 'No'], prompt='Playlist exists. Overwrite?', custominput=True)
            if esc_pressed(r) or none_selected(r) or r[0] == 'No':
                continue
            else:
                client.rm(name)
                client.save(name)

        break

def load_tracks(client, tracks, append=False):
    playlist = client.playlist()
    if not append:
        prompt_save_playlist(client)
        client.clear()
    for track in tracks:
        client.add(track['file'])

LOOP_END = 0
LOOP_CONT = 1

def search_add(client, query, command):
    if command == 'find':
        execute_query(client, query, client.findadd)
    else:
        execute_query(client, query, client.searchadd)
    return LOOP_END

def search_list(client, query, command):
    if command == 'find':
        s = execute_query(client, query, client.find)
    else:
        s = execute_query(client, query, client.search)
    tracks = [sformat_track(i, s[i]) for i in range(0,len(s))]
    dmenu(tracks, prompt='Selected')
    return LOOP_CONT

def search_select(client, query, command):
    if command == 'find':
        s = execute_query(client, query, client.find)
    else:
        s = execute_query(client, query, client.search)
    tracks = dmenu_select_tracks(s, 'Select:')
    if esc_pressed(tracks):
        return LOOP_CONT
    r = dmenu(['play', 'add'], prompt='Action')
    if esc_pressed(r) or none_selected(r):
        return LOOP_CONT
    action = r[0]
    if action == 'play':
        prompt_save_playlist(client)
        client.clear()
    load_tracks(client, tracks, append=True)
    mpd_resume(client, 'resume')
    return LOOP_END

def search_play(client, query, command):
    playlist = client.playlist()
    prompt_save_playlist(client)
    client.clear()
    search_add(client, query, command)
    mpd_resume(client, 'resume')
    return LOOP_END

search_actions = {
    'filter'         : build_query,
    'add'            : search_add,
    'list'           : search_list,
    'select'         : search_select,
    'play'           : search_play
}

# Covers both 'find' and 'search' command: extinguised by 'command' string
def mpd_search(client, command):
    query = build_query(client, command)
    if query == None or len(query) == 0:
        return None
    while True:
        r = dmenu(search_actions, prompt='Selection')
        if esc_pressed(r) or none_selected(r):
            return None
        action = r[0].lower()
        if action == 'filter':
            query = build_query(client, command, query=query)
        else:
            lc = search_actions[action](client, query, command)
            if lc != LOOP_CONT:
                break

def mpd_play(client, command):
    current = client.currentsong()
    playlist = client.playlistinfo()
    if current:
        playlist.remove(current)
        playlist.insert(0, current)
    tracks = dmenu_select_tracks(playlist, prompt='Play', usepos=True)
    if tracks == None:
        return
    client.play(tracks[0]['pos'])

# Wrapper function: uniform signature
def mpd_playlist_move_track(client, src, dst, name=''):
    if name:
        client.playlistmove(name, src, dst)
    else:
        client.move(src, dst)

def mpd_playlist_move_tracks(client, playlist, tracks, before=True, playlist_name=''):
    indices = sorted([int(t['pos']) for t in tracks])
    base_prompt = 'Move before:'
    prompt = base_prompt
    while True:
        r = dmenu_select_tracks(playlist, prompt=prompt, usepos=True, ranges=False)
        if esc_pressed(r) or none_selected(r):
            return
        to = int(r[0]['pos'])
        if to in indices:
            prompt='{} is to be moved. {}'.format(to, base_prompt)
            continue
        break
    adj = 0
    i = 0
    if before:
        to = max(0,to-1)
    while i < len(indices) and indices[i] <= to: # placed before pivot point
        mpd_playlist_move_track(client, indices[i]-adj, to)
        adj += 1
        i += 1
    to  = min(len(playlist)-1, to+1)
    while i < len(indices): # placed after pivot point
        mpd_playlist_move_track(client, indices[i], to)
        i += 1
        to += 1

current_playlist_actions = ['play', 'delete', 'crop', 'move before', 'move after']
def mpd_current_playlist(client, command):
    current = client.currentsong()
    playlist = client.playlistinfo()
    if current in playlist:
        playlist.remove(current)
        playlist.insert(0, current)
    tracks = dmenu_select_tracks(playlist, prompt='Playlist', usepos=True)

    if tracks == None:
        return
    while True:
        r = dmenu(current_playlist_actions, prompt='Action')
        if esc_pressed(r):
            return
        if not none_selected(r):
            break
    action = r[0]
    if action not in current_playlist_actions:
        return
    if action == 'play':
        client.play(tracks[0]['pos'])
    elif action == 'delete':
        indices = sorted([int(t['pos']) for t in tracks])
        adj = 0
        for i in indices:
            client.delete(i-adj)
            adj += 1
    elif action == 'crop':
        adj = 0
        for track in playlist:
            if track not in tracks:
                client.delete(int(track['pos'])-adj)
                adj += 1
    elif action in ['move before', 'move after']:
        before = (action == 'move before')
        mpd_playlist_move_tracks(client, playlist, tracks, before=before)
    return

playlist_list_actions = ['add', 'play', 'delete', 'crop']
def mpd_playlists_list(client, playlists):
    tracks = []
    for playlist in playlists:
        tracks += client.listplaylistinfo(playlist)
    while True:
        r = dmenu_select_tracks(tracks, 'Select Tracks:')
        if esc_pressed(r):
            return
        if none_selected(r):
            continue
        selected = r
        r = dmenu(playlist_list_actions, prompt='Actions')
        if esc_pressed(r) or none_selected(r):
            continue

        action = r[0]
        if action == 'add':
            for track in selected:
                client.add(track['file'])
            return LOOP_END
        elif action == 'play':
            load_tracks(client, tracks)
            mpd_resume(client, 'resume')
            return LOOP_END
        elif action == 'delete':
            for track in selected:
                tracks.remove(track)
            continue
        elif action == 'crop':
            for track in tracks:
                if track not in selected:
                    tracks.remove(track)

def mpd_playlists_rename(client, playlists):
    for playlist in playlists:
        prompt='Rename'
        while True:
            r = dmenu([playlist], prompt=prompt, custominput=True)
            if esc_pressed(r):
                break
            newname = r[0]
            if newname == '':
                continue
            try:
                client.rename(playlist, newname)
            except CommandError:
                prompt='{} exists. Rename'.format(newname)
                continue
            break

playlist_actions = ['add', 'play', 'remove', 'list', 'rename']
def mpd_playlists(client, command):
    playlists = client.listplaylists()
    playlists_list = [p['playlist'] for p in playlists]
    r = dmenu(playlists_list, "Playlists:")
    if esc_pressed(r) or none_selected(r):
        return
    playlists = r
    while 1:
        if len(playlists) > 1:
            prompt = 'Playlists: {} ...'.format(playlists[0])
        else:
            prompt = 'Playlist: {}'.format(playlists[0])
        r = dmenu(playlist_actions, prompt=prompt)
        if esc_pressed(r):
            break
        if none_selected(r):
            continue
        action = r[0]
        if action == 'add':
            for playlist in playlists:
                client.load(playlist)
        elif action == 'play':
            prompt_save_playlist(client)
            mpd_clear(client, command)
            for playlist in playlists:
                client.load(playlist)
            mpd_resume(client, 'resume')
        elif action == 'remove':
            for playlist in playlists:
                client.rm(playlist)
        elif action == 'list':
            rc = mpd_playlists_list(client, playlists)
            if rc == LOOP_CONT:
                continue
        elif action == 'rename':
            rc = mpd_playlists_rename(client, playlists)
        break

def mpd_save_playlist(client, command):
    save_playlist(client)

def set_volume(client, prev_volume):
    r = dmenu([prev_volume], prompt="Volume: ", custominput=True)
    if esc_pressed(r) or none_selected(r):
        return
    s = r[0].strip()
    val = int(s.strip('+- %\n\t'))
    prev_volume = int(prev_volume)
    if s[0]=='-':
        client.setvol(max(0,prev_volume-val))
    elif s[0]=='+':
        client.setvol(min(100,prev_volume+val))
    else:
        client.setvol(max(0,min(100,val)))

play_options = [('random', 'b'), ('repeat', 'b'), ('single', 'b'), ('consume', 'b'), ('volume', 'n')]
def mpd_options(client, command):
    status = client.status()
    opt_list = []
    for opt,t in play_options:
        value = status[opt]
        if t=='b':
            print_value = str((value == '1'))
        elif t=='n':
            if value == '-1':
                continue
            print_value = '{}%'.format(value)
        opt_list.append('{} : {}'.format(opt,print_value))
    selected = dmenu(opt_list, prompt='Options')
    selected = [i.split(' : ') for i in selected]
    for opt, value in selected:
        if opt in ['repeat', 'random', 'single', 'consume']:
            val = 1^int(status[opt])
        if opt == 'repeat':
            client.repeat(val)
        elif opt == 'random':
            client.random(val)
        elif opt == 'single':
            client.single(val)
        elif opt == 'consume':
            client.consume(val)
        elif opt == 'volume':
            set_volume(client, status['volume'])

def mpd_shuffle(client, command):
    playlist = client.playlistinfo()
    tracks = dmenu_select_tracks(playlist, prompt='Select range',
            usepos=True, ranges=False)
    if esc_pressed(tracks):
        return
    if none_selected(tracks) or len(tracks) < 2:
        client.shuffle()
    else:
        positions = [int(track['pos']) for track in tracks]
        a = min(positions)
        b = max(positions)+1
        client.shuffle('{}:{}'.format(a,b))

def mpd_seek(client, command):
    nc = 0
    while True:
        current, length = client.status()['time'].split(':')
        c = int(current)
        l = int(length)
        r = dmenu([current, length], prompt='Time', custominput=True)
        if esc_pressed(r) or none_selected(r):
            return
        ntime = r[0].strip()
        try:
            ptime = float(ntime.rstrip('%').lstrip('+-'))
        except ValueError:
            continue
        if ntime.endswith('%'):
            ntime = ntime.rstrip('%')
            frac = l*ptime/100
            if ntime.startswith('+'):
                nc = c + frac
            elif ntime.startswith('-'):
                nc = c - frac
            else:
                nc = frac
        else:
            if ntime.startswith('+'):
                nc = c + ptime
            elif ntime.startswith('-'):
                nc = c - ptime
            else:
                nc = ptime
        nc = max(0,min(int(length), nc))
        break
    client.seekcur(nc)

def mpd_update(client, command):
    client.update()


commands = {
    'resume'           : mpd_resume,
    'pause'            : mpd_pause,
    'stop'             : mpd_stop,
    'toggle'           : mpd_toggle,
    'previous'         : mpd_previous,
    'next'             : mpd_next,
    'clear'            : mpd_clear,
    'search'           : mpd_search,
    'find'             : mpd_search,
    'play'             : mpd_play,
    'current playlist' : mpd_current_playlist,
    'save playlist'    : mpd_save_playlist,
    'all playlists'    : mpd_playlists,
    'options'          : mpd_options,
    'shuffle'          : mpd_shuffle,
    'seek'             : mpd_seek,
    'update'           : mpd_update,
}

def main(address='localhost', port=6600, timeout=60):
    client = MPDClient();
    client.timeout = timeout;
    client.connect(address, port)

    while True:
        try:
                r = dmenu(commands.keys(), prompt='Action')
                if esc_pressed(r):
                    return
                if none_selected(r):
                    continue
                command = r[0]
                if command not in commands:
                    break
                commands[command](client, command.lower())
        except ConnectionError as e:
            r = dmenu(['retry', 'close'], prompt="Connection error")
            if esc_pressed(r) or none_selected(r) or r[0] == 'close':
                break
            client.connect(address, port)

    client.close()
    client.disconnect()




if __name__=='__main__':
    address = 'localhost'
    port = 6600
    timeout = 60
    try:
        opts, args = gnu_getopt(argv[1:], 'a:p:t:', ['address=', 'port=', 'timeout'])
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
        p = Popen(['which', 'dmenu'])
        p.wait()
        if p.returncode != 0:
            print('"which dmenu" returned {}'.format(p.returncode), file=stderr)
            exit(1);
    main(address=address, port=port, timeout=timeout)

