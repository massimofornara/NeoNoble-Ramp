import { bytesToHex, keccak256 } from "./keccak256.js";

const P = 0xfffffffffffffffffffffffffffffffffffffffffffffffffffffffefffffc2fn;
const N = 0xfffffffffffffffffffffffffffffffebaaedce6af48a03bbfd25e8cd0364141n;
const GX = 55066263022277343669578718895168534326250603453777594175500187360389116729240n;
const GY = 32670510020758816978083085130507043184471273380659243275938904335757337482424n;
const G = { x: GX, y: GY };

export function recoverPersonalSignAddress(message, signatureHex) {
  const signature = hexToBytes(signatureHex);
  if (signature.length !== 65) throw new Error("Invalid EVM signature length");
  const r = bytesToBigInt(signature.slice(0, 32));
  const s = bytesToBigInt(signature.slice(32, 64));
  let v = signature[64];
  if (v >= 27) v -= 27;
  const msg = new TextEncoder().encode(message);
  const prefix = new TextEncoder().encode(`\x19Ethereum Signed Message:\n${msg.length}`);
  const digest = bytesToBigInt(keccak256(concat(prefix, msg)));
  const pub = recoverPublicKey(digest, r, s, v);
  const pubBytes = concat(bigIntToBytes(pub.x, 32), bigIntToBytes(pub.y, 32));
  const address = bytesToHex(keccak256(pubBytes).slice(-20));
  return `0x${address}`;
}

function recoverPublicKey(e, r, s, recovery) {
  const x = r + BigInt(recovery >> 1) * N;
  if (x >= P) throw new Error("Invalid recovery id");
  const alpha = modPow((x ** 3n + 7n) % P, (P + 1n) / 4n, P);
  const y = (alpha & 1n) === BigInt(recovery & 1) ? alpha : P - alpha;
  const R = { x, y };
  if (!isOnCurve(R)) throw new Error("Recovered point is not on curve");
  const rInv = inv(r, N);
  const q = mul(add(mul(R, s), neg(mul(G, e))), rInv);
  if (!q) throw new Error("Invalid recovered public key");
  return q;
}

function add(a, b) {
  if (!a) return b;
  if (!b) return a;
  if (a.x === b.x && a.y !== b.y) return null;
  const m = a.x === b.x
    ? mod((3n * a.x * a.x) * inv(2n * a.y, P), P)
    : mod((b.y - a.y) * inv(b.x - a.x, P), P);
  const x = mod(m * m - a.x - b.x, P);
  const y = mod(m * (a.x - x) - a.y, P);
  return { x, y };
}

function mul(point, scalar) {
  let n = mod(scalar, N);
  let result = null;
  let addend = point;
  while (n > 0n) {
    if (n & 1n) result = add(result, addend);
    addend = add(addend, addend);
    n >>= 1n;
  }
  return result;
}

function neg(point) {
  return point ? { x: point.x, y: mod(-point.y, P) } : null;
}

function isOnCurve(point) {
  return mod(point.y * point.y - point.x * point.x * point.x - 7n, P) === 0n;
}

function inv(value, modulo) {
  let a = mod(value, modulo);
  let b = modulo;
  let x = 0n;
  let y = 1n;
  let u = 1n;
  let v = 0n;
  while (a !== 0n) {
    const q = b / a;
    [x, u] = [u, x - u * q];
    [y, v] = [v, y - v * q];
    [b, a] = [a, b - a * q];
  }
  return mod(x, modulo);
}

function modPow(base, exponent, modulo) {
  let result = 1n;
  let b = mod(base, modulo);
  let e = exponent;
  while (e > 0n) {
    if (e & 1n) result = (result * b) % modulo;
    b = (b * b) % modulo;
    e >>= 1n;
  }
  return result;
}

function mod(value, modulo) {
  const result = value % modulo;
  return result >= 0n ? result : result + modulo;
}

function hexToBytes(hex) {
  const clean = hex.startsWith("0x") ? hex.slice(2) : hex;
  return Uint8Array.from(clean.match(/.{1,2}/g).map((byte) => Number.parseInt(byte, 16)));
}

function bytesToBigInt(bytes) {
  return BigInt(`0x${bytesToHex(bytes)}`);
}

function bigIntToBytes(value, length) {
  const hex = value.toString(16).padStart(length * 2, "0");
  return hexToBytes(hex);
}

function concat(...arrays) {
  const total = arrays.reduce((sum, array) => sum + array.length, 0);
  const output = new Uint8Array(total);
  let offset = 0;
  for (const array of arrays) {
    output.set(array, offset);
    offset += array.length;
  }
  return output;
}
