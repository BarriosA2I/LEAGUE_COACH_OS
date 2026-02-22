import sharp from 'sharp';
import { logger } from '@league-coach/core';

const TAG = 'vision:loading-screen';

/**
 * Represents a rectangular region in the loading screen image.
 */
export interface CropRegion {
  x: number;
  y: number;
  w: number;
  h: number;
}

/**
 * A single champion slot parsed from the loading screen layout.
 */
export interface LoadingScreenSlot {
  region: CropRegion;
  team: 'blue' | 'red';
  slot: number; // 0-4 within the team
}

/**
 * LoL loading screen layout reference (1920x1080 base resolution):
 *
 * The loading screen shows 5 blue team champion portraits on the left
 * and 5 red team champion portraits on the right. Each portrait is a
 * vertical card arranged in a row on each side.
 *
 * Blue team portraits: left ~4% to ~46% of screen width
 * Red team portraits: right ~54% to ~96% of screen width
 *
 * Each portrait within a team is evenly spaced across ~42% of screen width,
 * so each card is roughly 8% wide with small gaps.
 *
 * Vertical position: portraits span roughly from 15% to 85% of screen height.
 */

// Layout ratios (relative to image dimensions)
const BLUE_START_X = 0.04;
const RED_START_X = 0.54;
const TEAM_WIDTH = 0.42;
const SLOT_COUNT = 5;
const SLOT_GAP_RATIO = 0.005; // gap between slots
const PORTRAIT_Y_START = 0.15;
const PORTRAIT_Y_END = 0.85;

function computeSlotRegion(
  imageWidth: number,
  imageHeight: number,
  team: 'blue' | 'red',
  slot: number,
): CropRegion {
  const teamStartX = team === 'blue' ? BLUE_START_X : RED_START_X;
  const totalTeamWidth = TEAM_WIDTH * imageWidth;
  const slotWidth = (totalTeamWidth - SLOT_GAP_RATIO * imageWidth * (SLOT_COUNT - 1)) / SLOT_COUNT;
  const gapWidth = SLOT_GAP_RATIO * imageWidth;

  const x = Math.round(teamStartX * imageWidth + slot * (slotWidth + gapWidth));
  const y = Math.round(PORTRAIT_Y_START * imageHeight);
  const w = Math.round(slotWidth);
  const h = Math.round((PORTRAIT_Y_END - PORTRAIT_Y_START) * imageHeight);

  return { x, y, w, h };
}

/**
 * FAST MODE implementation: parses a LoL loading screen image and returns
 * the 10 champion portrait crop regions based on the known fixed layout.
 *
 * Note: Actual champion recognition from the cropped portraits requires
 * ML/template matching, which is not implemented in FAST MODE. This
 * function provides the geometric regions for future use.
 *
 * @param imagePath - Absolute path to the loading screen screenshot
 * @returns Array of 10 LoadingScreenSlots with computed crop regions
 */
export async function parseLoadingScreen(imagePath: string): Promise<LoadingScreenSlot[]> {
  logger.info(TAG, `Parsing loading screen: ${imagePath}`);

  const metadata = await sharp(imagePath).metadata();
  const width = metadata.width!;
  const height = metadata.height!;

  logger.info(TAG, `Image dimensions: ${width}x${height}`);

  const slots: LoadingScreenSlot[] = [];

  for (let i = 0; i < SLOT_COUNT; i++) {
    slots.push({
      region: computeSlotRegion(width, height, 'blue', i),
      team: 'blue',
      slot: i,
    });
  }

  for (let i = 0; i < SLOT_COUNT; i++) {
    slots.push({
      region: computeSlotRegion(width, height, 'red', i),
      team: 'red',
      slot: i,
    });
  }

  logger.info(TAG, `Computed ${slots.length} portrait regions`);
  return slots;
}
