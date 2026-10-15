declare module '*.mjs' {
  export function buildPythonInvocation(code: string, methodName: string, input: unknown[], timeoutSeconds?: number): string;
}
