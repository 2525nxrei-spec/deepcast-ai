/**
 * functions/lib/crypto.js のテスト
 * Web Crypto APIはNode.js 20+のglobals.cryptoで利用可能
 */
import { describe, it, expect } from 'vitest';
import {
  hashPassword,
  generateSalt,
  generateId,
  createJWT,
  verifyJWT,
} from '../functions/lib/crypto.js';

describe('lib/crypto.js — 暗号ユーティリティ', () => {
  describe('hashPassword', () => {
    it('同じパスワード+ソルトで同じハッシュを返す', async () => {
      const salt = 'fixed-salt-for-test';
      const hash1 = await hashPassword('mypassword', salt);
      const hash2 = await hashPassword('mypassword', salt);
      expect(hash1).toBe(hash2);
    });

    it('異なるパスワードで異なるハッシュを返す', async () => {
      const salt = 'fixed-salt-for-test';
      const hash1 = await hashPassword('password1', salt);
      const hash2 = await hashPassword('password2', salt);
      expect(hash1).not.toBe(hash2);
    });

    it('異なるソルトで異なるハッシュを返す', async () => {
      const hash1 = await hashPassword('samepassword', 'salt-a');
      const hash2 = await hashPassword('samepassword', 'salt-b');
      expect(hash1).not.toBe(hash2);
    });

    it('ハッシュは64文字の16進数文字列', async () => {
      const hash = await hashPassword('test', 'salt');
      expect(hash).toMatch(/^[0-9a-f]{64}$/);
    });
  });

  describe('generateSalt', () => {
    it('32文字の16進数文字列を返す', () => {
      const salt = generateSalt();
      expect(salt).toMatch(/^[0-9a-f]{32}$/);
    });

    it('毎回異なる値を返す', () => {
      const salt1 = generateSalt();
      const salt2 = generateSalt();
      expect(salt1).not.toBe(salt2);
    });
  });

  describe('generateId', () => {
    it('UUID形式を返す', () => {
      const id = generateId();
      expect(id).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/);
    });

    it('毎回異なる値を返す', () => {
      const id1 = generateId();
      const id2 = generateId();
      expect(id1).not.toBe(id2);
    });
  });

  describe('JWT (createJWT / verifyJWT)', () => {
    const secret = 'test-jwt-secret';

    it('JWTを生成し検証できる', async () => {
      const payload = { sub: 'user-123', email: 'test@example.com', plan: 'free' };
      const token = await createJWT(
        { ...payload, exp: Math.floor(Date.now() / 1000) + 3600 },
        secret
      );

      expect(token).toMatch(/^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$/);

      const verified = await verifyJWT(token, secret);
      expect(verified).not.toBeNull();
      expect(verified.sub).toBe('user-123');
      expect(verified.email).toBe('test@example.com');
    });

    it('不正なシークレットで検証失敗', async () => {
      const token = await createJWT(
        { sub: 'user-1', exp: Math.floor(Date.now() / 1000) + 3600 },
        secret
      );
      const result = await verifyJWT(token, 'wrong-secret');
      expect(result).toBeNull();
    });

    it('有効期限切れのトークンはnull', async () => {
      const token = await createJWT(
        { sub: 'user-1', exp: Math.floor(Date.now() / 1000) - 100 },
        secret
      );
      const result = await verifyJWT(token, secret);
      expect(result).toBeNull();
    });

    it('不正な形式のトークンはnull', async () => {
      expect(await verifyJWT('invalid', secret)).toBeNull();
      expect(await verifyJWT('a.b', secret)).toBeNull();
      expect(await verifyJWT('', secret)).toBeNull();
    });
  });
});
