/** Appling's optional Baileys sidecar. stdout is private JSONL, never logs. */
import { createInterface } from 'node:readline';
import { mkdir, chmod } from 'node:fs/promises';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

export function selfMessage(message, account, normalize) {
  const remote = normalize(message.key?.remoteJid ?? '');
  const identities = [account?.id, account?.lid].filter(Boolean).map(normalize);
  if (!message.key?.fromMe || !identities.includes(remote)) return null;
  let body = message.message;
  body = body?.ephemeralMessage?.message ?? body;
  body = body?.viewOnceMessage?.message ?? body;
  const text = body?.conversation ?? body?.extendedTextMessage?.text;
  if (!text) return null;
  return { event: 'message', self_chat: true, from_me: true,
    account: normalize(account.id), message_id: message.key.id, text,
    reply_to: body?.extendedTextMessage?.contextInfo?.stanzaId ?? '' };
}

export async function main(authPath) {
  process.umask(0o077);
  const { default: makeWASocket, useMultiFileAuthState, DisconnectReason, jidNormalizedUser } = await import('baileys');
  const emit = data => process.stdout.write(`${JSON.stringify(data)}\n`);
  const auth = resolve(authPath);
  await mkdir(auth, { recursive: true, mode: 0o700 });
  await chmod(auth, 0o700);
  const { state, saveCreds } = await useMultiFileAuthState(auth);
  const logger = { level: 'silent', trace() {}, debug() {}, info() {}, warn() {}, error() {}, fatal() {}, child() { return this; } };
  let socket, closing = false, reconnectTimer, backoff = 1000;
  const sent = new Set();
  const connect = () => {
    if (closing) return;
    socket = makeWASocket({ auth: state, logger, markOnlineOnConnect: false,
      syncFullHistory: false, shouldSyncHistoryMessage: () => false });
    const current = socket;
    current.ev.on('creds.update', () => void saveCreds());
    current.ev.on('connection.update', update => {
      if (current !== socket || closing) return;
      if (update.qr) emit({ event: 'status', connected: false, qr: update.qr, message: 'Scan with WhatsApp → Linked devices. Then pair in Message yourself.' });
      if (update.connection === 'open') {
        backoff = 1000;
        emit({ event: 'status', connected: true, message: 'WhatsApp linked. Send the pairing code in Message yourself.' });
      }
      if (update.connection === 'close') {
        const loggedOut = update.lastDisconnect?.error?.output?.statusCode === DisconnectReason.loggedOut;
        emit({ event: 'status', connected: false, qr: '', message: loggedOut ? 'WhatsApp logged out. Disconnect and pair again.' : 'WhatsApp reconnecting…' });
        if (!loggedOut) {
          reconnectTimer = setTimeout(connect, backoff);
          backoff = Math.min(30000, backoff * 2);
        }
      }
    });
    current.ev.on('messages.upsert', ({ messages, type }) => {
      if (current !== socket || type !== 'notify') return;
      for (const message of messages) {
        if (sent.has(message.key?.id)) continue;
        const event = selfMessage(message, current.user, jidNormalizedUser);
        if (event) emit(event);
      }
    });
  };
  connect();
  const lines = createInterface({ input: process.stdin });
  lines.on('line', line => {
    void (async () => {
      let command;
      try {
        command = JSON.parse(line);
        if (command.method === 'logout') {
          closing = true;
          clearTimeout(reconnectTimer);
          await socket.logout();
          emit({ id: command.id, result: {} });
        } else if (command.method === 'send') {
          if (!socket.user?.id) throw new Error('Not linked');
          const result = await socket.sendMessage(jidNormalizedUser(socket.user.id), { text: String(command.text) });
          sent.add(result.key.id);
          if (sent.size > 2000) sent.delete(sent.values().next().value);
          emit({ id: command.id, result: { message_id: result.key.id } });
        } else {
          emit({ id: command.id, error: 'Unknown bridge method' });
        }
      } catch {
        emit({ id: command?.id, error: 'WhatsApp operation failed' });
      }
    })();
  });
  const stop = () => { closing = true; clearTimeout(reconnectTimer); socket?.end(undefined); process.exit(0); };
  process.on('SIGTERM', stop);
  lines.on('close', stop);
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  main(process.argv[2]).catch(() => { process.stdout.write(`${JSON.stringify({ event: 'status', connected: false, message: 'WhatsApp bridge failed to start. Check the installed Baileys dependency.' })}\n`); process.exit(1); });
}
