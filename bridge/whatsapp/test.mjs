import { test } from 'node:test';
import assert from 'node:assert/strict';
import { selfMessage } from './index.mjs';
const normalize = jid => jid.replace(/:\d+@/, '@');
const account = { id: '123:4@s.whatsapp.net', lid: 'abc@lid' };
test('only explicit owner self-chat messages reach the approval controller', () => {
  const message = { key: { remoteJid: '123@s.whatsapp.net', fromMe: true, id: 'one' }, message: { conversation: '/pair code' } };
  assert.equal(selfMessage(message, account, normalize).text, '/pair code');
  assert.equal(selfMessage({ ...message, key: { ...message.key, fromMe: false } }, account, normalize), null);
  assert.equal(selfMessage({ ...message, key: { ...message.key, remoteJid: 'stranger@s.whatsapp.net' } }, account, normalize), null);
  assert.equal(selfMessage({ ...message, key: { ...message.key, remoteJid: '123@g.us' } }, account, normalize), null);
});
test('linked identity and quoted reply preserve exact request mapping', () => {
  const message = { key: { remoteJid: 'abc@lid', fromMe: true, id: 'two' }, message: { extendedTextMessage: { text: 'yes', contextInfo: { stanzaId: 'request-message' } } } };
  const event = selfMessage(message, account, normalize);
  assert.equal(event.reply_to, 'request-message'); assert.equal(event.account, '123@s.whatsapp.net');
});
