import styles from './recorded-comparison-components.module.css';

const SYNTHETIC_PRODUCTS = Object.freeze([
  Object.freeze({
    name: '合成モデルA',
    verifiedFact: '合成検証値A',
    tradeOff: Object.freeze({
      benefit: '条件を明示した表示を確認できます。',
      limitation: '実商品・実測・推薦を表す値ではありません。',
      appliesWhen: 'ローカルの表示検証を行う場合',
    }),
  }),
  Object.freeze({
    name: '合成モデルB',
    verifiedFact: null,
    tradeOff: Object.freeze({
      benefit: '不明値を隠さない表示を確認できます。',
      limitation: '一次情報がないため値を比較できません。',
      appliesWhen: '欠損時の表示を確認する場合',
    }),
  }),
] as const);

export const RECORDED_COMPARISON_COMPONENT_CLASSIFICATION =
  'RECORDED_SYNTHETIC_ST1003_COMPONENT_FIXTURE_V2' as const;

export function RecordedUnknownValue() {
  return (
    <span className={styles['unknownValue']} data-state="unknown">
      <span aria-hidden="true" className={styles['unknownMark']}>
        ?
      </span>
      <span>不明（一次情報未確認）</span>
    </span>
  );
}

export function RecordedComparisonTable() {
  return (
    <section aria-labelledby="recorded-comparison-heading" className={styles['section']}>
      <div className={styles['sectionHeading']}>
        <p className={styles['eyebrow']}>RECORDED SYNTHETIC</p>
        <h2 id="recorded-comparison-heading">比較表の表示検証</h2>
        <p>実商品や推薦ではありません。見出し関係と不明値の表示を確認する合成fixtureです。</p>
      </div>
      <div
        aria-labelledby="recorded-comparison-heading"
        className={styles['tableRegion']}
        role="region"
        tabIndex={0}
      >
        <table className={styles['comparisonTable']}>
          <caption>合成モデル2件の比較表示</caption>
          <thead>
            <tr>
              <th scope="col">比較軸</th>
              {SYNTHETIC_PRODUCTS.map((product) => (
                <th key={product.name} scope="col">
                  {product.name}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            <tr>
              <th scope="row">確認項目</th>
              <td>{SYNTHETIC_PRODUCTS[0].verifiedFact}</td>
              <td>
                <RecordedUnknownValue />
              </td>
            </tr>
            <tr>
              <th scope="row">情報状態</th>
              <td>合成値のみ</td>
              <td>未確認</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  );
}

export function RecordedProductCards() {
  return (
    <section aria-labelledby="recorded-product-card-heading" className={styles['section']}>
      <div className={styles['sectionHeading']}>
        <p className={styles['eyebrow']}>RECORDED SYNTHETIC</p>
        <h2 id="recorded-product-card-heading">商品カードの表示検証</h2>
        <p>CTA、価格、在庫、画像、実商品情報は含みません。</p>
      </div>
      <div className={styles['cardGrid']}>
        {SYNTHETIC_PRODUCTS.map((product, index) => (
          <article className={styles['productCard']} key={product.name}>
            <p className={styles['syntheticLabel']}>合成検証用</p>
            <h3>{product.name}</h3>
            <dl className={styles['factList']}>
              <div>
                <dt>確認項目</dt>
                <dd>
                  {product.verifiedFact === null ? <RecordedUnknownValue /> : product.verifiedFact}
                </dd>
              </div>
            </dl>
            <section
              aria-labelledby={`recorded-trade-off-${String(index + 1)}`}
              className={styles['tradeOff']}
            >
              <h4 id={`recorded-trade-off-${String(index + 1)}`}>条件とトレードオフ</h4>
              <dl>
                <div>
                  <dt>利点</dt>
                  <dd>{product.tradeOff.benefit}</dd>
                </div>
                <div>
                  <dt>制約</dt>
                  <dd>{product.tradeOff.limitation}</dd>
                </div>
                <div>
                  <dt>当てはまる条件</dt>
                  <dd>{product.tradeOff.appliesWhen}</dd>
                </div>
              </dl>
            </section>
          </article>
        ))}
      </div>
    </section>
  );
}
