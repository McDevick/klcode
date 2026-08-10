export interface CommandState {
  running: boolean;
  taskId: string | null;
  sessionId: string | null;
}

export interface CommandArg {
  name: string;
  required?: boolean;
}

export interface CommandContext {
  state: CommandState;
}

export interface CommandDef {
  name: string;
  desc: string;
  usage?: string;
  args?: CommandArg[];
  aliases?: string[];
  available?: (state: CommandState) => boolean;
  handler: (ctx: CommandContext, args: string[]) => void;
}

export interface CommandResult {
  ok: boolean;
  error?: string;
  command?: CommandDef;
}

export class CommandRegistry {
  private readonly commands = new Map<string, CommandDef>();

  register(def: CommandDef): void {
    this.commands.set(def.name, def);
    for (const alias of def.aliases ?? []) {
      this.commands.set(alias, def);
    }
  }

  resolve(name: string): CommandDef | null {
    return this.commands.get(name) ?? null;
  }

  list(): CommandDef[] {
    const seen = new Set<string>();
    const commands: CommandDef[] = [];
    for (const def of this.commands.values()) {
      if (!seen.has(def.name)) {
        seen.add(def.name);
        commands.push(def);
      }
    }
    return commands;
  }

  run(name: string, args: string[], state: CommandState): CommandResult {
    const command = this.resolve(name);
    if (!command) {
      return { ok: false, error: `未知命令: ${name}` };
    }
    if (command.available && !command.available(state)) {
      return {
        ok: false,
        error: `${command.name}: 当前状态不可用`,
        command,
      };
    }
    for (let index = 0; index < (command.args ?? []).length; index += 1) {
      const arg = command.args![index];
      if (arg.required && args.length <= index) {
        return {
          ok: false,
          error: `${command.name}: 缺少参数 ${arg.name}\n用法: ${command.usage ?? command.name}`,
          command,
        };
      }
    }
    command.handler({ state }, args);
    return { ok: true, command };
  }
}
