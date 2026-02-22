import {
  type AgentDefinition,
  type AgentResult,
  VisionParseInputSchema,
  VisionParseOutputSchema,
  type VisionParseInput,
} from '@league-coach/core';
import { fastModeVision } from '@league-coach/vision';

export const visionParserAgent: AgentDefinition = {
  name: 'vision_parser',
  description: 'Parses a loading screen screenshot (or manual input) into structured champion slots for both teams.',
  inputSchema: VisionParseInputSchema,
  outputSchema: VisionParseOutputSchema,

  async execute(input: unknown): Promise<AgentResult> {
    const start = Date.now();
    try {
      const parsed = VisionParseInputSchema.parse(input) as VisionParseInput;
      const output = await fastModeVision(parsed);
      const validated = VisionParseOutputSchema.parse(output);

      return {
        agent: 'vision_parser',
        success: true,
        data: validated,
        duration_ms: Date.now() - start,
      };
    } catch (err) {
      return {
        agent: 'vision_parser',
        success: false,
        data: null,
        errors: [err instanceof Error ? err.message : String(err)],
        duration_ms: Date.now() - start,
      };
    }
  },
};
