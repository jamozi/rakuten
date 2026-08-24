import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import type {
  PublicEventInstrumentationEnvelopeV2,
  PublicEventInstrumentationRecordedFixtureV2,
} from '../../packages/web-ui/src/public-event-instrumentation.ts';

const repositoryRoot = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const recorded = JSON.parse(
  readFileSync(
    resolve(
      repositoryRoot,
      'changes/st-1202/generated/public-event-instrumentation-recorded.v2.json',
    ),
    'utf8',
  ),
) as { readonly recordedFixture: PublicEventInstrumentationRecordedFixtureV2 };

export function recordedFixture(): PublicEventInstrumentationRecordedFixtureV2 {
  return JSON.parse(
    JSON.stringify(recorded.recordedFixture),
  ) as PublicEventInstrumentationRecordedFixtureV2;
}

export function recordedEvents(): readonly PublicEventInstrumentationEnvelopeV2[] {
  return recordedFixture().events;
}
