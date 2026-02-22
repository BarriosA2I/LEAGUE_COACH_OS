import {
  logger,
  VisionParseInputSchema,
  type VisionParseInput,
  VisionParseOutputSchema,
  type VisionParseOutput,
} from '@league-coach/core';
import { recognizeChampions } from './champion-recognizer';

const TAG = 'vision:fast-mode';

/**
 * FAST MODE entry point for the vision pipeline.
 *
 * In FAST MODE the user provides champion names manually instead of
 * relying on image recognition. This is the primary path until ML-based
 * champion recognition is implemented.
 *
 * The orchestrator calls this function with a VisionParseInput that
 * includes manual_champions (array of 10 champion names: blue[0-4],
 * red[5-9], with index 0 being the user's champion).
 *
 * Flow:
 *   1. Validate input against VisionParseInputSchema
 *   2. Pass to champion-recognizer which validates names against vault data
 *   3. Validate output against VisionParseOutputSchema
 *   4. Return the validated VisionParseOutput
 *
 * @param input - Raw input (validated against VisionParseInputSchema)
 * @returns Validated VisionParseOutput with team rosters
 * @throws ZodError if input or output validation fails
 */
export async function fastModeVision(input: VisionParseInput): Promise<VisionParseOutput> {
  logger.info(TAG, 'FAST MODE vision pipeline started', {
    imagePath: input.image_path,
    manualCount: input.manual_champions?.length ?? 0,
  });

  // Step 1: Validate input
  const validatedInput = VisionParseInputSchema.parse(input);

  // Step 2: Recognize champions (uses manual_champions in FAST MODE)
  const result = await recognizeChampions(validatedInput);

  // Step 3: Validate output
  const validatedOutput = VisionParseOutputSchema.parse(result);

  logger.info(TAG, 'FAST MODE vision pipeline complete', {
    userChampion: validatedOutput.user_champion,
    userConfidence: validatedOutput.user_confidence,
    unknownSlots: validatedOutput.unknown_slots.length,
  });

  return validatedOutput;
}
