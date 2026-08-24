import { createPublicPolicyMetadata } from '../../src/public-policy';
import { PublicPolicyPage } from '../../src/public-shell';

export const dynamic = 'force-dynamic';
export const metadata = createPublicPolicyMetadata('PUB-006');

export default function PrivacyPolicyPage() {
  return <PublicPolicyPage screenId="PUB-006" />;
}
