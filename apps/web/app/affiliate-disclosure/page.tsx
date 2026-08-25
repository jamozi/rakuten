import { createPublicPolicyMetadata } from '../../src/public-policy';
import { PublicPolicyPage } from '../../src/public-shell';

export const dynamic = 'force-dynamic';
export const metadata = createPublicPolicyMetadata('PUB-005');

export default function AffiliateDisclosurePage() {
  return <PublicPolicyPage screenId="PUB-005" />;
}
