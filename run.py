import argparse
from datetime import timedelta
from hashlib import sha1
import logging
import sys

from beaker.cache import CacheManager
from beaker.util import parse_cache_config_options

import urlify
from gmusicapi import Mobileclient

def hash_metadata(d):
    return urlify.urlify(d).replace('-', '')

def track_metadata(track, k):
    return hash_metadata(track['track'][k])

def filter_songs(songs, query):
    s = filter(lambda x: x.get('best_result', False), songs)
    if s: return s

    q = hash_metadata(query)

    s = filter(lambda x: (track_metadata(x, 'artist') in q or track_metadata(x, 'albumArtist') in q) and track_metadata(x, 'title') in q, songs)
    if len(s) == 1: return s
    else:
        s = filter(lambda x: 'greatest-hits' not in track_metadata(x, 'album'), s)
        if s: return s

    return songs

##########

log = logging.getLogger()
frmttr = frmttr = logging.Formatter('%(asctime)s %(name)s %(levelname)s %(message)s', '%Y-%m-%d %H:%M:%S')
shdlr = logging.StreamHandler(sys.stdout)
shdlr.setFormatter(frmttr)
log.addHandler(shdlr)

##########

parser = argparse.ArgumentParser(description='Transforms text files to Play Music playlists')

parser.add_argument("--user", '-u', metavar='EMAIL', required=True)
parser.add_argument("--password", '-p', metavar='PASSWORD', required=True)
parser.add_argument("--verbose", '-v', action="store_true", default=False)

parser.add_argument('file', metavar='FILENAME', type=argparse.FileType('r'), help='a file to parse')
parser.add_argument('playlist', metavar='PLAYLIST_FILENAME', help='a filelist to create')

options = parser.parse_args()

##########

log.setLevel(logging.DEBUG if options.verbose else logging.WARN)

##########

cache_opts = {
    'cache.type': 'ext:database',
    'cache.url': "sqlite:///gmusic.s3db",
    'cache.data_dir': '.',
    'cache.expire': int(timedelta(days=3).total_seconds())
}
cache = CacheManager(**parse_cache_config_options(cache_opts))

def cached_search(cache, api, query):
    c = cache.get_cache('%s.search_all_access' % api.__class__.__name__)

    return c.get(key=sha1(query.encode('utf-8')).hexdigest(), createfunc=lambda: api.search_all_access(query))

##########

api = Mobileclient()

if not api.login(options.user, options.password):
    log.critical('Not logged in')
    sys.exit(100)

log.debug('Logged in')

songs_ids = []

for line in options.file.readlines():
    line = line.strip().decode('utf-8')
    if not line:
        continue

    log.info('Searching for %s', line)

    result = cached_search(cache, api, line)
    songs = result['song_hits']

    songs = filter_songs(songs, line)

    if len(songs):
        songs_ids.append(songs[0]['track']['storeId'])
        continue

    log.debug(songs)

for pl in api.get_all_playlists():
    if pl['name'] == options.playlist:
        api.delete_playlist(pl['id'])

playlist_id = api.create_playlist(options.playlist)
try:
    api.add_songs_to_playlist(playlist_id, songs_ids)
except Exception, _:
    api.delete_playlist(playlist_id)
