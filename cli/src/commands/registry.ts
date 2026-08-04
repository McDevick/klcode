export interface Command {
  name: string;
  aliases: string[];
  run: (args: string[]) => string | Promise<string>;
}

export class CommandRegistry {
  private commands: Command[] = [];

  register(command: Command): void {
    this.commands.push(command);
  }

  resolve(input: string): Command {
    const name = input.toLowerCase();
    const found = this.commands.find((c) => c.name === name || c.aliases.includes(name));
    if (!found) throw new Error(`unknown command: ${input}`);
    return found;
  }

  help(): string {
    return this.commands.map((c) => `/${c.name}`).join('\n');
  }
}
