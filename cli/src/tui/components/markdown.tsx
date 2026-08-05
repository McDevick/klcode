import React from 'react';
import { Box, Text } from 'ink';
import { marked, type Tokens } from 'marked';

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
              <Text key={key} color="yellow">
                {(token as Tokens.Codespan).text}
              </Text>
            );
          case 'link':
            return (
              <Text key={key} color="blue" underline>
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

function renderToken(token: Tokens.Generic, index: number) {
  const key = `token-${index}`;
  switch (token.type) {
    case 'heading': {
      const heading = token as Tokens.Heading;
      return (
        <Text key={key} bold color="cyan">
          {heading.text}
        </Text>
      );
    }
    case 'code': {
      const code = token as Tokens.Code;
      return (
        <Box key={key} flexDirection="column" borderStyle="single" borderColor="gray" paddingX={1}>
          <Text color="green">{code.text}</Text>
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
              {item.text}
            </Text>
          ))}
        </Box>
      );
    }
    case 'blockquote': {
      const quote = token as Tokens.Blockquote;
      return (
        <Text key={key} color="gray">
          ▍{quote.text}
        </Text>
      );
    }
    case 'hr':
      return <Text key={key} color="gray">───</Text>;
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
