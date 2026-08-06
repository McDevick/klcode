import React from 'react';
import { Box, Text } from 'ink';
import { marked, type Tokens } from 'marked';
import { theme } from '../theme';

function InlineContent({ tokens }: { tokens: Tokens.Generic[] }) {
  return (
    <>
      {tokens.map((token, index) => {
        const key = `inline-${index}`;
        switch (token.type) {
          case 'strong':
            return (
              <Text key={key} bold>
                {(token as Tokens.Strong).text}
              </Text>
            );
          case 'em':
            return (
              <Text key={key} italic>
                {(token as Tokens.Em).text}
              </Text>
            );
          case 'codespan':
            return (
              <Text key={key} color={theme.yellow}>
                {(token as Tokens.Codespan).text}
              </Text>
            );
          case 'link':
            return (
              <Text key={key} color={theme.teal} underline>
                {(token as Tokens.Link).text}
              </Text>
            );
          default:
            return <Text key={key}>{(token as Tokens.Text).text ?? ''}</Text>;
        }
      })}
    </>
  );
}

function collectInlineTokens(tokens: Tokens.Generic[]): Tokens.Generic[] {
  return tokens.flatMap((token) => {
    const nested = (token as Tokens.Generic & { tokens?: Tokens.Generic[] }).tokens;
    if (nested && nested.some((item) => ['strong', 'em', 'codespan', 'link'].includes(item.type))) {
      return nested;
    }
    return [token];
  });
}

function renderToken(token: Tokens.Generic, index: number) {
  const key = `token-${index}`;
  switch (token.type) {
    case 'heading': {
      const heading = token as Tokens.Heading;
      return (
        <Text key={key} bold color={theme.teal}>
          <InlineContent tokens={heading.tokens ?? []} />
        </Text>
      );
    }
    case 'code': {
      const code = token as Tokens.Code;
      return (
        <Box key={key} flexDirection="column" borderStyle="single" borderColor={theme.surfaceAlt} paddingX={1}>
          <Text color={theme.green}>{code.text}</Text>
        </Box>
      );
    }
    case 'paragraph': {
      const paragraph = token as Tokens.Paragraph;
      return (
        <Text key={key}>
          <InlineContent tokens={paragraph.tokens ?? []} />
        </Text>
      );
    }
    case 'list': {
      const list = token as Tokens.List;
      return (
        <Box key={key} flexDirection="column">
          {list.items.map((item, itemIndex) => (
            <Text key={`${key}-${itemIndex}`}>
              {list.ordered ? `${itemIndex + 1}. ` : '- '}
              <InlineContent tokens={collectInlineTokens(item.tokens ?? [])} />
            </Text>
          ))}
        </Box>
      );
    }
    case 'blockquote': {
      const quote = token as Tokens.Blockquote;
      return (
        <Text key={key} color={theme.textDim}>
          ▍<InlineContent tokens={collectInlineTokens(quote.tokens ?? [])} />
        </Text>
      );
    }
    case 'hr':
      return <Text key={key} color={theme.textDim}>───</Text>;
    case 'space':
      return null;
    default:
      return <Text key={key}>{(token as Tokens.Text).text ?? ''}</Text>;
  }
}

export function MarkdownRenderer({ text }: { text: string }) {
  const tokens = marked.lexer(text);
  return <Box flexDirection="column">{tokens.map(renderToken)}</Box>;
}
