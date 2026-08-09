export type JsonPrimitive = null | boolean | number | string;

export type JsonArray = readonly JsonValue[];

export type JsonObject = {
  readonly [key: string]: JsonValue;
};

export type JsonValue = JsonPrimitive | JsonArray | JsonObject;

export const JSON_VALIDATION_CODES = [
  'JSON_UNSUPPORTED_TYPE',
  'JSON_NON_FINITE_NUMBER',
  'JSON_NON_PLAIN_OBJECT',
  'JSON_DANGEROUS_KEY',
  'JSON_CYCLIC_REFERENCE',
  'JSON_SYMBOL_KEY',
  'JSON_INVALID_PROPERTY',
  'JSON_INVALID_ARRAY',
  'JSON_STRUCTURE_UNREADABLE',
] as const;

export type JsonValidationCode = (typeof JSON_VALIDATION_CODES)[number];

export class JsonValidationError extends TypeError {
  readonly code: JsonValidationCode;

  constructor(code: JsonValidationCode) {
    super(code);
    this.name = 'JsonValidationError';
    this.code = code;
    Object.freeze(this);
  }
}

const DANGEROUS_KEYS = new Set(['__proto__', 'constructor', 'prototype']);
const ARRAY_INDEX = /^(?:0|[1-9][0-9]*)$/;

function reject(code: JsonValidationCode): never {
  throw new JsonValidationError(code);
}

function readPrototype(value: object): object | null {
  try {
    return Object.getPrototypeOf(value);
  } catch {
    return reject('JSON_STRUCTURE_UNREADABLE');
  }
}

function readOwnKeys(value: object): readonly (string | symbol)[] {
  try {
    return Reflect.ownKeys(value);
  } catch {
    return reject('JSON_STRUCTURE_UNREADABLE');
  }
}

function readDescriptor(value: object, key: string): PropertyDescriptor {
  let descriptor: PropertyDescriptor | undefined;
  try {
    descriptor = Object.getOwnPropertyDescriptor(value, key);
  } catch {
    return reject('JSON_STRUCTURE_UNREADABLE');
  }
  if (descriptor === undefined) {
    return reject('JSON_STRUCTURE_UNREADABLE');
  }
  return descriptor;
}

function readArrayIdentity(value: object): boolean {
  try {
    return Array.isArray(value);
  } catch {
    return reject('JSON_STRUCTURE_UNREADABLE');
  }
}

function requireDataProperty(descriptor: PropertyDescriptor): unknown {
  if (!descriptor.enumerable || !Object.hasOwn(descriptor, 'value')) {
    return reject('JSON_INVALID_PROPERTY');
  }
  return descriptor.value;
}

function cloneArray(value: object, ancestors: WeakSet<object>): JsonArray {
  if (readPrototype(value) !== Array.prototype) {
    return reject('JSON_NON_PLAIN_OBJECT');
  }

  const lengthDescriptor = readDescriptor(value, 'length');
  if (
    lengthDescriptor.enumerable ||
    !Object.hasOwn(lengthDescriptor, 'value') ||
    typeof lengthDescriptor.value !== 'number'
  ) {
    return reject('JSON_INVALID_ARRAY');
  }

  const length = lengthDescriptor.value;
  const indexedValues = new Map<number, unknown>();
  for (const key of readOwnKeys(value)) {
    if (typeof key === 'symbol') {
      return reject('JSON_SYMBOL_KEY');
    }
    if (key === 'length') {
      continue;
    }
    if (!ARRAY_INDEX.test(key)) {
      return reject('JSON_INVALID_ARRAY');
    }
    const index = Number(key);
    if (!Number.isSafeInteger(index) || index < 0 || index >= length) {
      return reject('JSON_INVALID_ARRAY');
    }
    indexedValues.set(index, requireDataProperty(readDescriptor(value, key)));
  }

  if (indexedValues.size !== length) {
    return reject('JSON_INVALID_ARRAY');
  }

  const clone: JsonValue[] = [];
  for (let index = 0; index < length; index += 1) {
    if (!indexedValues.has(index)) {
      return reject('JSON_INVALID_ARRAY');
    }
    clone.push(cloneJson(indexedValues.get(index), ancestors));
  }
  return Object.freeze(clone);
}

function cloneObject(value: object, ancestors: WeakSet<object>): JsonObject {
  const prototype = readPrototype(value);
  if (prototype !== Object.prototype && prototype !== null) {
    return reject('JSON_NON_PLAIN_OBJECT');
  }

  const values = new Map<string, unknown>();
  for (const key of readOwnKeys(value)) {
    if (typeof key === 'symbol') {
      return reject('JSON_SYMBOL_KEY');
    }
    if (DANGEROUS_KEYS.has(key)) {
      return reject('JSON_DANGEROUS_KEY');
    }
    values.set(key, requireDataProperty(readDescriptor(value, key)));
  }

  const clone: Record<string, JsonValue> = {};
  for (const key of [...values.keys()].sort()) {
    const descriptorValue = values.get(key);
    Object.defineProperty(clone, key, {
      configurable: false,
      enumerable: true,
      value: cloneJson(descriptorValue, ancestors),
      writable: false,
    });
  }
  return Object.freeze(clone);
}

function cloneJson(value: unknown, ancestors: WeakSet<object>): JsonValue {
  if (value === null || typeof value === 'string' || typeof value === 'boolean') {
    return value;
  }
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) {
      return reject('JSON_NON_FINITE_NUMBER');
    }
    return Object.is(value, -0) ? 0 : value;
  }
  if (typeof value !== 'object') {
    return reject('JSON_UNSUPPORTED_TYPE');
  }

  if (ancestors.has(value)) {
    return reject('JSON_CYCLIC_REFERENCE');
  }
  ancestors.add(value);
  try {
    return readArrayIdentity(value) ? cloneArray(value, ancestors) : cloneObject(value, ancestors);
  } finally {
    ancestors.delete(value);
  }
}

export function assertJsonValue(value: unknown): asserts value is JsonValue {
  cloneJson(value, new WeakSet<object>());
}

export function createJsonValue(value: unknown): JsonValue {
  return cloneJson(value, new WeakSet<object>());
}
