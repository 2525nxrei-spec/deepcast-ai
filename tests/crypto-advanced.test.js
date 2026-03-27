/**
 * crypto.js 高度なテスト
 * JWT生成・検証の追加パターン、ハッシュの一貫性テスト
 */
import { describe, it, expect } from 'vitest';
import { hashPassword, generateSalt, generateId, createJWT, verifyJWT } from '../functions/lib/crypto.js';

describe('crypto.js — 高度なテスト', () => {
  describe('hashPassword', () => {
    it('同じパスワード・ソルトで同じハッシュが得られる（決定論的）', async () => {
      const hash1 = await hashPassword('testpass123', 'fixed-salt');
      const hash2 = await hashPassword('testpass123', 'fixed-salt');
      expect(hash1).toBe(hash2);
    });

    it('異なるソルトで異なるハッシュが得られる', async () => {
      const hash1 = await hashPassword('testpass123', 'salt-a');
      const hash2 = await hashPassword('testpass123', 'salt-b');
      expect(hash1).not.toBe(hash2);
    });

    it('異なるパスワードで異なるハッシュが得られる', async () => {
      const hash1 = await hashPassword('password1', 'same-salt');
      const hash2 = await hashPassword('password2', 'same-salt');
      expect(hash1).not.toBe(hash2);
    });

    it('ハッシュは64文字の16進数文字列', async () => {
      const hash = await hashPassword('test', 'salt');
      expect(hash).toMatch(/^[0-9a-f]{64}$/);
    });

    it('空パスワードでもハッシュ生成は可能', async () => {
      const hash = await hashPassword('', 'salt');
      expect(hash).toMatch(/^[0-9a-f]{64}$/);
    });

    it('日本語パスワードでもハッシュ生成可能', async () => {
      const hash = await hashPassword('パスワード123', 'salt');
      expect(hash).toMatch(/^[0-9a-f]{64}$/);
    });
  });

  describe('generateSalt', () => {
    it('32文字の16進数文字列', () => {
      const salt = generateSalt();
      expect(salt).toMatch(/^[0-9a-f]{32}$/);
    });

    it('呼び出すたびに異なる値', () => {
      const salt1 = generateSalt();
      const salt2 = generateSalt();
      expect(salt1).not.toBe(salt2);
    });
  });

  describe('generateId', () => {
    it('UUID形式', () => {
      const id = generateId();
      expect(id).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/);
    });

    it('呼び出すたびに異なる値', () => {
      const id1 = generateId();
      const id2 = generateId();
      expect(id1).not.toBe(id2);
    });
  });

  describe('JWT createJWT / verifyJWT', () => {
    const secret = 'test-secret-key';

    it('作成と検証のラウンドトリップ', async () => {
      const payload = { sub: 'user-1', email: 'test@test.com', exp: Math.floor(Date.now() / 1000) + 3600 };
      const token = await createJWT(payload, secret);
      const verified = await verifyJWT(token, secret);
      expect(verified.sub).toBe('user-1');
      expect(verified.email).toBe('test@test.com');
    });

    it('異なるシークレットで検証失敗: null', async () => {
      const token = await createJWT({ sub: 'user-1', exp: Math.floor(Date.now() / 1000) + 3600 }, secret);
      const result = await verifyJWT(token, 'wrong-secret');
      expect(result).toBeNull();
    });

    it('改竄されたペイロード: null', async () => {
      const token = await createJWT({ sub: 'user-1', exp: Math.floor(Date.now() / 1000) + 3600 }, secret);
      const parts = token.split('.');
      // ペイロード部分を改竄
      const tamperedPayload = btoa(JSON.stringify({ sub: 'admin', plan: 'pro' }))
        .replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
      const tampered = `${parts[0]}.${tamperedPayload}.${parts[2]}`;
      const result = await verifyJWT(tampered, secret);
      expect(result).toBeNull();
    });

    it('期限切れトークン: null', async () => {
      const token = await createJWT({ sub: 'user-1', exp: Math.floor(Date.now() / 1000) - 1 }, secret);
      const result = await verifyJWT(token, secret);
      expect(result).toBeNull();
    });

    it('exp未設定のトークン: 有効（期限チェックなし）', async () => {
      const token = await createJWT({ sub: 'user-1', email: 'no-exp@test.com' }, secret);
      const result = await verifyJWT(token, secret);
      expect(result).not.toBeNull();
      expect(result.sub).toBe('user-1');
    });

    it('空文字列トークン: null', async () => {
      const result = await verifyJWT('', secret);
      expect(result).toBeNull();
    });

    it('ドット1つのトークン: null', async () => {
      const result = await verifyJWT('abc.def', secret);
      expect(result).toBeNull();
    });

    it('ドット3つのトークン: null', async () => {
      const result = await verifyJWT('a.b.c.d', secret);
      expect(result).toBeNull();
    });

    it('日本語を含むペイロード', async () => {
      const payload = { sub: 'user-1', display_name: '太郎', exp: Math.floor(Date.now() / 1000) + 3600 };
      const token = await createJWT(payload, secret);
      const result = await verifyJWT(token, secret);
      expect(result.display_name).toBe('太郎');
    });
  });
});
