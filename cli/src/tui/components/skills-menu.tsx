import React from 'react';
import { Box, Text } from 'ink';
import type { SkillInfo } from '../../api/client';
import { CommandMenu } from './command-menu';
import { theme } from '../theme';

export function SkillsMenu({
  skills,
  menuIndex,
  loading,
  error,
}: {
  skills: SkillInfo[];
  menuIndex: number;
  loading: boolean;
  error: string;
}) {
  if (loading) {
    return (
      <Box paddingX={1} backgroundColor={theme.surface}>
        <Text dimColor>正在加载 skills…</Text>
      </Box>
    );
  }
  if (error) {
    return (
      <Box paddingX={1} backgroundColor={theme.surface}>
        <Text color={theme.red}>skills 加载失败: {error}</Text>
      </Box>
    );
  }
  if (skills.length === 0) {
    return (
      <Box paddingX={1} backgroundColor={theme.surface}>
        <Text dimColor>暂无可用 skill</Text>
      </Box>
    );
  }
  return (
    <CommandMenu
      commands={skills.map((skill) => ({
        name: skill.name,
        desc: skill.description,
      }))}
      menuIndex={menuIndex}
    />
  );
}
