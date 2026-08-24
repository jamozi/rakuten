import { createPublicPolicyMetadata } from '../../src/public-policy';
import { PublicPolicyPage } from '../../src/public-shell';

export const dynamic = 'force-dynamic';
export const metadata = createPublicPolicyMetadata('PUB-007');

export default function AboutPage() {
  return <PublicPolicyPage screenId="PUB-007" />;
}
