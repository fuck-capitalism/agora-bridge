#!/usr/bin/env python3
# Copyright 2021 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# an [[agora bridge]], that is, a utility that takes a .yaml file describing a set of [[personal knowledge graphs]] or [[digital gardens]] and pulls them to be consumed by other bridges or an [[agora server]]. 
# -- [[flancian]]

import argparse
import glob
import logging
import os
import pickle
import random
import re
import time
import tweepy
import yaml

# Globals.
WIKILINK_RE = re.compile(r'\[\[(.*?)\]\]', re.IGNORECASE)
PUSH_RE = re.compile(r'\[\[push\]\]\s(\S+)', re.IGNORECASE)
HELP_RE = re.compile(r'\[\[help\]\]\s(\S+)', re.IGNORECASE)
# Unused for now.
P_HELP = 0.2

parser = argparse.ArgumentParser(description='Agora Bot for Twitter.')
parser.add_argument('--config', dest='config', type=argparse.FileType('r'), required=True, help='The path to agora-bot.yaml, see agora-bot.yaml.example.')
parser.add_argument('--output-dir', dest='output_dir', type=argparse.FileType('r'), required=False, help='The path to a directory where data will be dumped as needed.')
parser.add_argument('--verbose', dest='verbose', type=bool, default=False, help='Whether to log more information.')
parser.add_argument('--dry-run', dest='dry_run', action="store_true", help='Whether to refrain from posting or making changes.')
args = parser.parse_args()

logging.basicConfig()
L = logging.getLogger('agora-bot')
if args.verbose:
    L.setLevel(logging.DEBUG)
else:
    L.setLevel(logging.INFO)

def slugify(wikilink):
    # trying to keep it light here for simplicity, wdyt?
    # c.f. util.py in [[agora server]].
    slug = (
            wikilink.lower()
            .strip()
            .replace(' ', '-')
            )
    return slug

def already_replied(api, tweet, upto=1):
    # tweets = api.user_timeline(since_id=tweet.id, count=200, include_rts=1, tweet_mode='extended')
    # amazing that this is needed, but oh well.
    tweets = tweepy.Cursor(api.search, since_id=tweet.id, q='to:'+tweet.user.screen_name+' from:an_agora', result_type='recent', timeout=999999).items(1000)
    count = 0
    for t in tweets:
        if t.in_reply_to_status_id == tweet.id:
            count += 1
            if count == upto:
                L.info(f"{tweet.id}: cancelling reply, we seem to have already replied")
                return True
    L.info(f"{tweet.id}: reply pending")
    return False

def reply_to_tweet(api, reply, tweet):
    # Twitter deduplication only *mostly* works so we can't depend on it.
    # Alternatively it might be better to implement state/persistent cursors, but this is easier.
    # TODO: move all of these to a class so we don't have to keep passing 'api' around.
    if already_replied(api, tweet):
        L.info("*** refrained to tweet thanks to dedup logic")
        return False

    if args.dry_run:
        L.info("*** refrained to tweet thanks to dry run")
        return False

    try:
        return api.update_status(
            status=reply,
            in_reply_to_status_id=tweet.id,
            auto_populate_reply_metadata=True
            )
    except tweepy.error.TweepError as e:
        # triggered by duplicates, for example.
        L.debug(f'error while replying: {e}')
        return False

def handle_wikilink(api, tweet, match=None):
    L.debug(f'seen wikilink, tweet: {tweet.full_text}, match: {match}')
    wikilinks = WIKILINK_RE.findall(tweet.full_text)
    lines = []
    for wikilink in wikilinks:
        slug = slugify(wikilink)
        lines.append(f'https://anagora.org/{slug}')

    response = '\n'.join(lines)
    L.debug(f'tweeting: "{response}" as response to tweet id {tweet.id}')
    if reply_to_tweet(api, response, tweet):
        L.info(f'replied to {tweet.id}')

def handle_push(api, tweet, match=None):
    L.debug(f'seen push: {tweet}, {match}')
    reply_to_tweet(api, 'If you ask the Agora to [[push]], it will try to push for you.', tweet)

def handle_help(api, tweet, match=None):
    L.info(f'seen help: {status}, {match}')
    reply_to_tweet(api, 'If you tell the Agora about a [[wikilink]], it will try to resolve it for you and mark your resource as relevant to the entity described between double square brackets. See https://anagora.org/agora-bot for more!', tweet, upto=2)
    reply_to_tweet(api, 'If you ask the Agora to [[push]], it will try to push for you.', tweet, upto=2)

def follow_followers(api):
    L.info("Retrieving and following followers")
    if args.dry_run:
        return False

    for follower in tweepy.Cursor(api.followers).items():
        if not follower.following:
            L.info(f"Following {follower.name}")
            follower.follow()

def check_mentions(api, since_id):
    # from https://realpython.com/twitter-bot-python-tweepy/
    L.info("Retrieving mentions")
    new_since_id = since_id
    tweets = list(tweepy.Cursor(api.mentions_timeline, since_id=since_id, count=200, tweet_mode='extended').items())
    L.info(f'*** Processing up to {len(tweets)} mentions.')
    for tweet in tweets:
        L.debug(f'Processing tweet: {tweet.full_text}')
        new_since_id = max(tweet.id, new_since_id)
        if not tweet.user.following and not args.dry_run:
            L.info('Following ', tweet.user)
            tweet.user.follow()
        # Process commands, in order of priority
        cmds = [
                (HELP_RE, handle_help),
                (PUSH_RE, handle_push),
                (WIKILINK_RE, handle_wikilink),
                ]
        for regexp, handler in cmds:
            match = regexp.search(tweet.full_text.lower())
            if match:
                handler(api, tweet, match)
                break
    return new_since_id

#class AgoraBot(tweepy.StreamListener):
#    """main class for [[agora bot]] for [[twitter]]."""
#    # this follows https://docs.tweepy.org/en/stable/streaming_how_to.html
#
#    def on_status(self, status):
#        L.info('received status: ', status.text)
#
#    def __init__(self, mastodon):
#        StreamListener.__init__(self)
#        self.mastodon = mastodon
#        L.info('[[agora bot]] started!')
#
#    def send_toot(self, msg, in_reply_to_id=None):
#        L.info('sending toot.')
#        status = self.mastodon.status_post(msg, in_reply_to_id=in_reply_to_id)
#
#    def handle_wikilink(self, status, match=None):
#        L.info(f'seen wikilink: {status}, {match}')
#        wikilinks = WIKILINK_RE.findall(status.content)
#        lines = []
#        for wikilink in wikilinks:
#            slug = slugify(wikilink)
#            lines.append(f'https://anagora.org/{slug}')
#        self.send_toot('\n'.join(lines), status)
#
#    def handle_push(self, status, match=None):
#        L.info(f'seen push: {status}, {match}')
#        self.send_toot('If you ask the Agora to [[push]], it will try to push for you.', status)
#
#    def handle_mention(self, status):
#        """Handle toots mentioning the [[agora bot]], which may contain commands"""
#        L.info('Got a mention!')
#        # Process commands, in order of priority
#        cmds = [(PUSH_RE, self.handle_push),
#                (WIKILINK_RE, self.handle_wikilink)]
#        for regexp, handler in cmds:
#            match = regexp.search(status.content)
#            if match:
#                handler(status, match)
#                return
#
#    def on_notification(self, notification):
#        self.last_read_notification = notification.id
#        if notification.type == 'mention':
#            self.handle_mention(notification.status)
#        else:
#            L.info(f'received unhandled notification type: {notification.type}')

def main():
    try:
        config = yaml.safe_load(args.config)
    except yaml.YAMLError as e:
        L.error(e)

    # Set up Twitter API.
    CONSUMER_SECRET = config['consumer_secret']
    ACCESS_TOKEN_SECRET = config['access_token_secret']

    auth = tweepy.OAuthHandler("lwDT7dRWwntKfadnkt0dOgYDE", CONSUMER_SECRET)
    auth.set_access_token("1315647335158943746-EI7o9RElt2MN2zIXHwnM49trpuqCSV", ACCESS_TOKEN_SECRET)

    api = tweepy.API(auth)
    since_id = 1
    L.info('[[agora bot]] starting.')
    # api.update_status('[[agora bot]] v0.9 for Twitter starting, please wait.')

    while True: 
        try: 
            follow_followers(api)
        except tweepy.error.TweepError:
            # this limit is easy to hit when ~20-30 people are in the backlog.
            pass
        since_id = check_mentions(api, since_id)
        L.info('[[agora bot]] waiting.')
        time.sleep(10)

if __name__ == "__main__":
    main()
