"""Run an independent outbound notification process.

Never accepts remote trade approval via SMS, email, Discord or Slack.
"""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
import json
import logging
import os
from pathlib import Path
import signal
import time
from quantlab.delivery.channels import channels_from_environment,Message
from quantlab.delivery.dispatcher import AlertReader,DeliveryLedger,NotificationDispatcher

log=logging.getLogger('quantlab.notify')


def build():
    sql=os.getenv('QUANTLAB_ALERT_DB') or None
    reader=AlertReader(sql,Path(os.getenv('QUANTLAB_ALERTS_FILE','artifacts/alerts.jsonl')))
    ledger=DeliveryLedger(os.getenv('QUANTLAB_DELIVERY_DB') or sql or 'artifacts/notifications.sqlite')
    return NotificationDispatcher(reader,ledger,channels_from_environment(),
                  max_signal_age=int(os.getenv('QUANTLAB_NOTIFICATION_MAX_AGE_SECONDS','600')))


def main():
    parser=argparse.ArgumentParser(description='QuantLab outbound alerts (not trade execution)')
    mode=parser.add_mutually_exclusive_group()
    mode.add_argument('--once',action='store_true',help='Process current alert journal once')
    mode.add_argument('--check',action='store_true',help='Print configured channel names only')
    mode.add_argument('--send-test',action='store_true',help='Send real test notice to configured destinations')
    parser.add_argument('--confirm-send',action='store_true',help='Required for --send-test')
    parser.add_argument('--poll-seconds',type=int,default=5)
    args=parser.parse_args()
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
    dispatch=build()
    names=[c.name for c in dispatch.channels]
    if args.check:
        print(json.dumps({'channels':names,'count':len(names),'delivery_state':dispatch.ledger.summary()}));return
    if not names:
        raise SystemExit('No channels configured. Set QUANTLAB_DISCORD_WEBHOOK_URL, SMS, SMTP or Slack secrets.')
    if args.send_test:
        if not args.confirm_send:raise SystemExit('--send-test requires --confirm-send')
        msg=Message('local-test','NONE','','','','','','',0,'CHANNEL_TEST')
        for channel in dispatch.channels:
            try:
                channel.send(msg)
                print(f'{channel.name}: provider accepted test')
            except Exception as exc:
                print(f'{channel.name}: FAILED ({type(exc).__name__}); check provider logs and secrets')
        return
    if args.once:
        print(json.dumps(dispatch.run_once()));return
    if not 1<=args.poll_seconds<=300:raise SystemExit('poll-seconds must be 1..300')
    stopping=False
    def stop(*_):
        nonlocal stopping
        stopping=True
    signal.signal(signal.SIGINT,stop);signal.signal(signal.SIGTERM,stop)
    log.info('QuantLab notifier started, channels=%s',','.join(names))
    while not stopping:
        result=dispatch.run_once()
        if result['sent'] or result['failed']:
            log.info('Alert deliveries accepted=%s failed=%s',result['sent'],result['failed'])
        for _ in range(args.poll_seconds):
            if stopping:break
            time.sleep(1)

if __name__=='__main__':main()
