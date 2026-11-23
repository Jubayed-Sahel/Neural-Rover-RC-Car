"""Pair a private Telegram chat without exposing the bot token."""
import getpass
import json
import secrets
import sys

from telegram_alerts import SETTINGS, call_bot, load_alert_settings, send_text


def main():
    if sys.argv[1:] == ['--test']:
        settings = load_alert_settings()
        if not settings:
            raise RuntimeError('Set up Telegram first.')
        send_text(settings, 'Neural Rover: Telegram notification test.')
        print('Test message sent to the paired private chat.')
        return
    print('Create a dedicated bot with @BotFather using /newbot in Telegram.')
    token = getpass.getpass('Bot token (hidden): ').strip()
    bot = call_bot(token, 'getMe', {})
    code = f'rover-{secrets.token_hex(5)}'
    print(f"Open @{bot['username']} on your phone, press Start, then send this exact pairing code: {code}")
    input('Press Enter after sending the code...')
    updates = call_bot(token, 'getUpdates', {'allowed_updates': ['message'], 'timeout': 0})
    for update in reversed(updates):
        message = update.get('message', {})
        chat = message.get('chat', {})
        if chat.get('type') == 'private' and message.get('text') == code:
            SETTINGS.write_text(json.dumps({'token': token, 'chat_id': chat['id']}), encoding='utf-8')
            print('Paired. Run 11_TEST_TELEGRAM.bat to send yourself one test notification.')
            return
    raise RuntimeError('Pairing code not found. Run setup again and send the new code in the private bot chat.')


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, OSError, ValueError) as error:
        raise SystemExit(str(error))
