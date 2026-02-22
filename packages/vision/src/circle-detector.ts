import { logger } from '@league-coach/core';
import type { CropRegion } from './loading-screen-parser';

const TAG = 'vision:circle-detector';

/**
 * FAST MODE stub: circle detection is not implemented.
 *
 * Future implementation plan:
 * 1. Load image via sharp and extract raw pixel data
 * 2. Apply color analysis to find drawn circle overlays (typically bright
 *    colors like red, yellow, or green that contrast with the loading screen)
 * 3. Use contour detection on the filtered color mask to identify circular
 *    shapes above a minimum radius threshold
 * 4. Return the bounding box of the detected circle, which indicates
 *    which champion portrait the user has circled
 *
 * When this returns null, the system falls back to manual champion input
 * via the manual_champions field in VisionParseInput.
 *
 * @param _imagePath - Absolute path to the loading screen screenshot
 * @returns null (no circle detected in FAST MODE)
 */
export async function detectCircledRegion(_imagePath: string): Promise<CropRegion | null> {
  logger.info(TAG, 'Circle detection not implemented in FAST MODE, returning null');
  return null;
}
