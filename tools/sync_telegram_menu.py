#!/usr/bin/env python3
"""Retry only menu registration; never reinstall or log a Telegram token."""
import argparse,json,pathlib,re,sys,urllib.request

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):raise ValueError('redirect refused')

PUBLIC_COMMANDS = [{'command':'help','description':'查看帮助'},
                   {'command':'whoami','description':'查看身份与权限'}]
OWNER_COMMANDS = PUBLIC_COMMANDS + [
    {'command':cmd,'description':description} for cmd,description in [
        ('model','切换模型'),('new','开启新会话'),('clear','重置上下文'),
        ('stop','终止任务'),('status','查看状态'),('summary','总结发言')]]

def sync(env_file,opener=None):
    path=pathlib.Path(env_file)
    if path.is_symlink() or not path.is_file() or path.stat().st_mode&0o077:
        raise ValueError('private env file required')
    values={}
    for line in path.read_text().splitlines():
        key,sep,value=line.partition('=')
        if sep and key in {'TELEGRAM_BOT_TOKEN','TELEGRAM_ALLOWED_USERS'}:
            values[key]=json.loads(value) if value.startswith('"') else value
    token=values.get('TELEGRAM_BOT_TOKEN','');owner=str(values.get('TELEGRAM_ALLOWED_USERS',''))
    if not re.fullmatch(r'[0-9]{7,12}:[A-Za-z0-9_-]{30,50}',token):raise ValueError('invalid bot token')
    if not re.fullmatch(r'[1-9][0-9]*',owner):raise ValueError('invalid owner ID')
    opener=opener or urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
    scopes=[({'type':kind},PUBLIC_COMMANDS) for kind in ('default','all_private_chats','all_group_chats')]
    scopes.append(({'type':'chat','chat_id':int(owner)},OWNER_COMMANDS))
    for scope,commands in scopes:
        request=urllib.request.Request('https://api.telegram.org/bot'+token+'/setMyCommands',
            json.dumps({'commands':commands,'scope':scope}).encode(),
            {'Content-Type':'application/json'},method='POST')
        with opener.open(request,timeout=10) as response:
            if json.load(response).get('ok') is not True:raise RuntimeError('menu rejected')
    print('SUCCESS: Telegram menus synchronized; authorization remains in gateway config.')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--env-file',default=str(pathlib.Path.home()/'.hermes/.env'));args=parser.parse_args()
    try:sync(args.env_file)
    except Exception as error:
        print('FAILED: Telegram menu '+type(error).__name__,file=sys.stderr);sys.exit(1)
