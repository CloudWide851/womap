import type { RasterFormulaNode } from '../../types/imports';

type Token =
  | { kind: 'number'; value: number }
  | { kind: 'band'; value: number }
  | { kind: 'identifier'; value: string }
  | { kind: 'symbol'; value: '+' | '-' | '*' | '/' | '^' | '(' | ')' | ',' }
  | { kind: 'end' };

const functionArity = {
  abs: 1,
  sqrt: 1,
  log: 1,
  min: 2,
  max: 2,
  clamp: 3,
} as const;

export function supportsRasterWebGLPreview(node: RasterFormulaNode): boolean {
  if (node.kind === 'unary') return supportsRasterWebGLPreview(node.argument);
  if (node.kind === 'binary') {
    return supportsRasterWebGLPreview(node.left) && supportsRasterWebGLPreview(node.right);
  }
  if (node.kind === 'function') {
    return node.name !== 'log' && node.arguments.every(supportsRasterWebGLPreview);
  }
  return true;
}

export function formatRasterFormula(node: RasterFormulaNode): string {
  if (node.kind === 'band') return `B${node.band}`;
  if (node.kind === 'number') return String(node.value);
  if (node.kind === 'unary') return `${node.operator}(${formatRasterFormula(node.argument)})`;
  if (node.kind === 'binary') {
    return `(${formatRasterFormula(node.left)}${node.operator}${formatRasterFormula(node.right)})`;
  }
  return `${node.name}(${node.arguments.map(formatRasterFormula).join(', ')})`;
}

function tokenize(source: string): Token[] {
  const tokens: Token[] = [];
  let index = 0;
  while (index < source.length) {
    const rest = source.slice(index);
    const whitespace = /^\s+/.exec(rest);
    if (whitespace) {
      index += whitespace[0].length;
      continue;
    }
    const band = /^B(\d+)/i.exec(rest);
    if (band) {
      tokens.push({ kind: 'band', value: Number(band[1]) });
      index += band[0].length;
      continue;
    }
    const number = /^(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?/i.exec(rest);
    if (number) {
      tokens.push({ kind: 'number', value: Number(number[0]) });
      index += number[0].length;
      continue;
    }
    const identifier = /^[A-Za-z_][A-Za-z0-9_]*/.exec(rest);
    if (identifier) {
      tokens.push({ kind: 'identifier', value: identifier[0].toLowerCase() });
      index += identifier[0].length;
      continue;
    }
    const symbol = rest[0];
    if ('+-*/^(),'.includes(symbol)) {
      tokens.push({ kind: 'symbol', value: symbol as Extract<Token, { kind: 'symbol' }>['value'] });
      index += 1;
      continue;
    }
    throw new Error(`公式包含无法识别的字符：${symbol}`);
  }
  tokens.push({ kind: 'end' });
  return tokens;
}

export function parseRasterFormula(source: string): RasterFormulaNode {
  const tokens = tokenize(source.trim());
  let cursor = 0;
  const peek = () => tokens[cursor] ?? ({ kind: 'end' } as const);
  const consume = () => tokens[cursor++] ?? ({ kind: 'end' } as const);

  const parsePrimary = (): RasterFormulaNode => {
    const token = consume();
    if (token.kind === 'number') return { kind: 'number', value: token.value };
    if (token.kind === 'band') {
      if (token.value < 1 || token.value > 256) throw new Error('波段编号必须在 B1 到 B256 之间。');
      return { kind: 'band', band: token.value };
    }
    if (token.kind === 'symbol' && (token.value === '+' || token.value === '-')) {
      return { kind: 'unary', operator: token.value, argument: parsePrimary() };
    }
    if (token.kind === 'symbol' && token.value === '(') {
      const value = parseExpression(0);
      const closing = consume();
      if (closing.kind !== 'symbol' || closing.value !== ')') throw new Error('公式缺少右括号。');
      return value;
    }
    if (token.kind === 'identifier') {
      if (!(token.value in functionArity)) throw new Error(`不支持函数 ${token.value}。`);
      const opening = consume();
      if (opening.kind !== 'symbol' || opening.value !== '(') throw new Error('函数后必须使用括号。');
      const argumentsList: RasterFormulaNode[] = [];
      while (true) {
        argumentsList.push(parseExpression(0));
        const separator = consume();
        if (separator.kind === 'symbol' && separator.value === ')') break;
        if (separator.kind !== 'symbol' || separator.value !== ',') throw new Error('函数参数格式无效。');
      }
      const name = token.value as keyof typeof functionArity;
      if (argumentsList.length !== functionArity[name]) {
        throw new Error(`${name} 需要 ${functionArity[name]} 个参数。`);
      }
      return { kind: 'function', name, arguments: argumentsList };
    }
    throw new Error('公式表达式不完整。');
  };

  const bindingPower = (token: Token): [number, number] | null => {
    if (token.kind !== 'symbol') return null;
    if (token.value === '+' || token.value === '-') return [10, 11];
    if (token.value === '*' || token.value === '/') return [20, 21];
    if (token.value === '^') return [30, 30];
    return null;
  };

  function parseExpression(minimumBindingPower: number): RasterFormulaNode {
    let left = parsePrimary();
    while (true) {
      const power = bindingPower(peek());
      if (!power || power[0] < minimumBindingPower) break;
      const operator = consume() as Extract<Token, { kind: 'symbol' }>;
      const right = parseExpression(power[1]);
      left = {
        kind: 'binary',
        operator: operator.value as '+' | '-' | '*' | '/' | '^',
        left,
        right,
      };
    }
    return left;
  }

  if (!source.trim()) throw new Error('请输入波段公式。');
  const result = parseExpression(0);
  if (peek().kind !== 'end') throw new Error('公式尾部包含多余内容。');
  return result;
}
