export interface Command {
  name: string;
  aliases: string[];
  run: (args: string[]) => string | Promise<string>;
}

export class CommandRegistry {
  private commands: Command[] = [];

  register(command: Command): void {
    const normalized: Command = {
      ...command,
      name: normalize(command.name),
      aliases: command.aliases.map(normalize),
    };
    const keys = new Set([normalized.name, ...normalized.aliases]);
    const exists = this.commands.some((existing) => {
      const existingKeys = new Set([existing.name, ...existing.aliases]);
      return [...keys].some((key) => existingKeys.has(key));
    });
    if (exists) {
      throw new Error(`duplicate command: ${command.name}`);
    }
    this.commands.push(normalized);
  }

  resolve(input: string): Command {
    const name = normalize(input);
    const found = this.commands.find((c) => c.name === name || c.aliases.includes(name));
    if (!found) throw new Error(`unknown command: ${input}`);
    return found;
  }

  help(): string {
    return this.commands
      .map((command) => {
        const names = [command.name, ...command.aliases];
        return names.map((name) => `/${name}`).join(', ');
      })
      .join('\n');
  }
}

function normalize(input: string): string {
  return input.trim().replace(/^\/+/, '').toLowerCase();
}
