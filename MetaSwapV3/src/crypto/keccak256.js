const MASK_64 = (1n << 64n) - 1n;
const ROT = [
  [0, 36, 3, 41, 18],
  [1, 44, 10, 45, 2],
  [62, 6, 43, 15, 61],
  [28, 55, 25, 21, 56],
  [27, 20, 39, 8, 14]
];
const RC = [
  1n, 0x8082n, 0x800000000000808an, 0x8000000080008000n, 0x808bn,
  0x80000001n, 0x8000000080008081n, 0x8000000000008009n, 0x8an,
  0x88n, 0x80008009n, 0x8000000an, 0x8000808bn, 0x800000000000008bn,
  0x8000000000008089n, 0x8000000000008003n, 0x8000000000008002n,
  0x8000000000000080n, 0x800an, 0x800000008000000an,
  0x8000000080008081n, 0x8000000000008080n, 0x80000001n,
  0x8000000080008008n
];

export function keccak256(data) {
  const bytes = data instanceof Uint8Array ? data : new TextEncoder().encode(String(data));
  const state = new Array(25).fill(0n);
  const rate = 136;
  const padded = Array.from(bytes);
  padded.push(0x01);
  while ((padded.length % rate) !== rate - 1) padded.push(0);
  padded.push(0x80);

  for (let offset = 0; offset < padded.length; offset += rate) {
    for (let lane = 0; lane < rate / 8; lane++) {
      let value = 0n;
      for (let i = 0; i < 8; i++) value |= BigInt(padded[offset + lane * 8 + i]) << BigInt(8 * i);
      state[lane] ^= value;
    }
    permute(state);
  }

  const output = new Uint8Array(32);
  for (let lane = 0; lane < 4; lane++) {
    const value = state[lane];
    for (let i = 0; i < 8; i++) output[lane * 8 + i] = Number((value >> BigInt(8 * i)) & 0xffn);
  }
  return output;
}

export function keccak256Hex(data) {
  return bytesToHex(keccak256(data));
}

export function bytesToHex(bytes) {
  return Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
}

function rot(value, shift) {
  const n = BigInt(shift);
  return ((value << n) | (value >> (64n - n))) & MASK_64;
}

function permute(state) {
  for (let round = 0; round < 24; round++) {
    const c = new Array(5);
    const d = new Array(5);
    for (let x = 0; x < 5; x++) c[x] = state[x] ^ state[x + 5] ^ state[x + 10] ^ state[x + 15] ^ state[x + 20];
    for (let x = 0; x < 5; x++) d[x] = c[(x + 4) % 5] ^ rot(c[(x + 1) % 5], 1);
    for (let x = 0; x < 5; x++) for (let y = 0; y < 5; y++) state[x + 5 * y] ^= d[x];
    const b = new Array(25);
    for (let x = 0; x < 5; x++) {
      for (let y = 0; y < 5; y++) {
        b[y + 5 * ((2 * x + 3 * y) % 5)] = rot(state[x + 5 * y], ROT[x][y]);
      }
    }
    for (let x = 0; x < 5; x++) {
      for (let y = 0; y < 5; y++) {
        state[x + 5 * y] = b[x + 5 * y] ^ ((~b[((x + 1) % 5) + 5 * y]) & b[((x + 2) % 5) + 5 * y]);
      }
    }
    state[0] ^= RC[round];
  }
}
