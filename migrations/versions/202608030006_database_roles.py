"""Install the exact ST-0306 database role and grant contract.

Revision ID: 202608030006
Revises: 202608030005
Create Date: 2026-08-05

RAOS metadata:
- story: ST-0306
- requirement IDs: FR-020
- architecture: RAOS-SEC-001 database workload-role boundary
- runner version: 1.5.0
- server version: 180004
- risk class: B (cluster roles plus database-local grants/default ACLs/RLS policies)
- estimated lock: bounded catalog ACL and RLS policy updates
- backfill job: none
- rollback category: database-local authority reversible; cluster roles preserved
- transaction: one PostgreSQL transaction for the complete Story revision
- rollback: drop 22 policies and revoke all Story-local grants/default ACLs
"""

from __future__ import annotations

import base64
import hashlib
import json
import zlib
from typing import Any

from alembic import op

revision: str = "202608030006"
down_revision: str | None = "202608030005"
branch_labels: tuple[str, ...] | None = None
depends_on: tuple[str, ...] | None = None
runner_version: str = "1.5.0"
story_id: str = "ST-0306"
server_version_num: int = 180004
_PAYLOAD_SHA256 = "5e4b61d71989ee7fedd71bb64d9b03807d07b1e1f446337e29295215c73f1449"
_MAX_PAYLOAD_BYTES = 512 * 1024

_PAYLOAD_B85: tuple[bytes, ...] = (
    b"c-rkf4R7N%vVVnG+=HD$^-J-3heLaNfa55;zIyGPKe}CX3qh8cSY282NpiBmyZi4)QeXU%M9EfSrwZD&",
    b"EzJyv!{Kl^B!~b1#`Yh*`@po}n;(9Cv(T4dG8+viAcSUMZH%26ZNOWwyEiN|GF|`v$2S@U<@(kaBXYLT",
    b"-$w|n_vg#Y%Wc@hK-crxEx4Uc#-mSQ=Nh&XTCN}N187*j7s0QQ5kS)hvnhbK6ZwH-x&t$a9Lt3gU^R;7",
    b"&N+bKofCwSu`xZ{FvAd13_dtE^ei}_AmG;>3>^G423Db$vUf1K09t-vtMV5^D^XPAu#n&uN#5jzmo*0U",
    b"wgOjZ$8yv#3iein8rL>#q@|Lgd5Ep)Id?ErAtvxrhZgivy&|)SEBf^V3_{2Es;G$Us1Zqf0s`ImwvT%9",
    b"Q%MJ;q1KLPJKnt_&B89IMzWl}>>C4DT<KEA>Jm#U62a}xH6vIez6_)WwL-zwA@;N@WedMnq*BaIIT2!B",
    b"y~qfy4cy9<o&!*(BrsG=Xs-V}`$-4G$pqZa$3KrJ`a6Ark@1t|@M?m7ji+ESdar*N0)H23z%jQP*!e+p",
    b"=ev%tfn>DPGE=DKC2PQRFtF=bPv~>McAap8)L8>}0Sq@D3=u)oGu<a7G4%D$@k~Mi3uEis&;>X1*#{7q",
    b"erRkRH25OAm3%Msf3EcD=p0$USxraF@oai#te=;VPfV{-cQt~?Gt_ED#!pYD6&OD!0iT#YKl;HJ7@Vg{",
    b"tMh((TCK+WnTh$tbQ{f%(L5iyQD>^(_4q$M9arc748?t7y1oni-=P(unZkMMdOiM6PuJD?KSOb!nyzDX",
    b"%Lx2))N^ItPf*8|ct0~SpO|h35SNOu&r`i?v446RuFU@V3H#LID0@QoJhi+A^CuWjQDgoDc^yuc`W#&A",
    b"H^bFrNwdp{79>?#=o5Xk#8pXDzr_1dpp0bD66H*=EzwU}t0n5G3baK&)vK21n@(%3ihDp?#ItVIQUO_C",
    b"ZA<K_0ceZ=*s8QdJvUVf^l4ADIc*JrEc7}0T-{y|m%4_iO!TF$Qm5avH~U>HdtqkaPo%&wy8OS(zo1IG",
    b"@K2w;Ykf2s&h^h8K!5%^guw%}Df)xmJpm2>XFmJ5{B*1T_}RPC-;Jj+Mk35_P>q+f9G_HALIiw#ug`UW",
    b"zI)~tVh))FrrwV+)$t9O&X(Y2wwhjp<$FCT4F8ShI+7@u&n7y%IE64KGsGAAT&!;O`3kiF;tG{FUZQ6)",
    b"-t|@Xl~9<@=KAeqJR0I*AN{)ebUR!u=95Ljh(1{$Ueam}5Z{*Rp$a)3n9Z5z;eH1L{17uvzi_+_44f#d",
    b"0f%QH9g3j6mOsZrE5bw`B~n%sYYzWv{j@W~FmS`dQhm>Jovjmrzx^G2`yK!K!E_ya??sLa#tTxT>1r}5",
    b"A$I57(~w-7&4=TK4)k9}`Yn<3YB8R^1NwYEnqBKeO|hQ#H1I)REQasMqs5YFDQ+cWxLnT1SF5FNd>Ai2",
    b"440$#siNpeKgKt?*66>C7t00c=Vd1f`khQA&3&{nws5<KK?sHmkbK=ZyBt4O*!;~P{)$-aC!~F+xxQb-",
    b"1zj9jV6)Zo3ilo3gZ|-4pD*5zZv}~=FP}ZpBAmLZh*$2K7>XFPGZUSeI2SXK=z3=)>IyDf1#My{GUU!w",
    b"bf)55OhvBoowcYdJ7z7piN#<DbXKFY8s}m)Sk3P&M_u_bv708AgCWpaj?QwNi{)T7zq1^*<(Ed98(EDM",
    b"xw9CZ#W)*_k!gHqE$YgS-aOL8V9@xT&FE~#x!4Rw?>n<mJARz)$Z51*l3{lyqca(2vu2X({An7D?qGO#",
    b"FuXe$-W?3@4u*FJ!@Gmw-NEqgV0d>hygL})9SrXdhIa?UyMy7~!SL>2cy}<oI~d*_4DSwxcL&2?<H7KR",
    b"*JQbA#vYTkVzk@U)nq*4YF5+*R1m2X=k*Iv!YWV^CARQ!_4;fnVaeF4L=?`tH)s@fTp5ds=-i?C`fMs=",
    b"%9vC_=1<<&=TRM1#-tjyaDcx7o9ehyKGo3kOaS#cR6&xlR)xnV5opp^)DYzzr5abvL(tI3Dk4kyRKyoj",
    b"8q{aC2Cj@#MRXxILIZtN$Caw38akI`p@BSAF{RQ}K^C$p)Mv5=u8hq>^l!ff!(Fx+<bQ{^W4z-44!}49",
    b"9(;fSK@Afp<Xhi!pFkd#0nsM#_xBrMf_31VHUjq_J@hZ$Boc!RK6~%x!|4*N$X)}+DQMqa!yd|V#xH%v",
    b"49Rm@lzK@=B8454BazA-i6aqA2mK?F%ZBG;(aVO>BN0S{-_e?a3{}UXmJcXLqL>^0V~H*^(8uC1F{UE9",
    b"#LDGqW?nQ{AYD(7YpnmGk5(~@sU1dT4DR<Px%mf~&If24p}!9-XzWbu3yk^~bkPYYF3C+0OjimLn`C0Q",
    b"4a@Xw$2KEa2^j^Z7drTB|3V^YG#-2;E2(4{0C#=>Y#6~{>v&FxgaCf`*C7&#4NTkIp%-DHfhVoeazmsQ",
    b"U{-$*Ht&a16V3ABG<nN>I7PuYAAzJ`pAV-=ndoD*3}dB_Ku|Q)hZ7ZT^%2A<nCm0(S=JA080}}X*9?Qm",
    b"*v<CQ+W!jjRduj2L*SV~;6EZ)H?;g6w86jja1X%_o52uYfK+PqGGPcy^{j|<(ITXQPZ%+f%k4$PZyg{@",
    b"t4b<vt(27GVM+nCptH+q8D@lUxk?_8m}OjAaUn=Px4EzX7&yq@gRS{Q<^&*o3K78&_;(<_td0x|cx$<d",
    b"L>|C<h-L!j+J!MVnSQ7VPFVLXoI%t@5$&=fB5!;Z(F6;tiYJ&+MMTP0DvN|Mh^knk)l<Y2O`B@f1pB30",
    b"B4?x&(egQS1!A6XvC^|>MnOT*D<~-IeFYuGZcsr*wO3S;QSBrZbgKJIrF2!gP!$p79#ug|xr0@SMYX?G",
    b"@uSxLs#A+r1jY*K<6$gbLkpm1!vGCpP6!-wvmt^qT{O_6*J$vHeA?H@9gyLeax2I%msTpi7_oR*ldwl`",
    b"`cM*J1r1cadAi0P&&=@HPUdgLe3h<kGX5AP5Q&QNtNZmdtChl~^Ux$JAUcj>fQnho<?B=AJC$Rh(g(Z1",
    b"@hoSDtHS&wC#UeWyUxA0CC(pyy+-o*V%)pvd2$u7Vo`A&2l0oo-g~wS)0z*0y_?-Dnmzp2-gKSl$v~QH",
    b"eKCT4{^l;eLRNr8UU85UeKZ|JGW&UtuTiz3<={e8na(2?0csHV$jC!{o04bVrNI*BAszY%J#!as{HPEh",
    b"alYyDeAiu@SS)qgAiLU`iSy)w&)!?E>1_GmM*7o0Ht9=2k*L#O!#i{DMgVEjgX1E1I|SQ(7=bke@GG?T",
    b"5t_KHpFp%hRtldWj3e{W#*DzD<GLU|CJOHM_?~6pud&g@217BkJzwdhmls-L#kBS<kj<T+7Ko=FQ46Fq",
    b")6@p-%y(*mIC7|3X-48@wLv)_T3Vo<`(tg0I`c}};5>11S|FYKG*!eKr>s|XE30ag?BqK1((KRP&1@d~",
    b"Lrl~?IiKB+f<3$dAIHo00M%slQ}RTG1Jw(_V-^xo3n4pAQh!Z!w6yprIG;j+u7#B6`Zu2+Q(_HnZ$Axb",
    b")xNsE6{)3Vlt@m>#tTVr3!{y1`)FK#5(SriW58OF9!*{poB|s!tb3dkKYP-Kr=iyIgrN-;<b_$6n-`L0",
    b"2z|_xX(KmLR7K`(3mVAK7geyh_?MCvdS&71h;0-Ij04!3o^uDo=%_;D%8<ydl#3U$dA4KXc{7@63UZ@f",
    b"9@oO<Wr|`F3Vk8T+&MuQ85`5HlWBZz&C-cC1p>eBVBnDXcMN?@fr+f-woILumzQIvW-6>7UF`%$RE7BR",
    b"x@bG0<@zDA9kCPtH7XfeMc`vfQNl{ez*@x1^T?6i<w|C3F=Ew}N8`a{o_;Y9=hO;-rA}NSS&5S(z{<vE",
    b"5vX7w5&$VvT*#H!!YQbVWm1DpJ7B&ES>vYpT7#`Aoj#noK9uht?V9)%HL=P7AzNLk-XT-ICeta<^C(c>",
    b"(){XdVemE?+$CG57yNM*J{xTat$l!(BuUy)vWmwir`<Z?7Vm094DP)Mtetzui`Z<m;~P2wC!!b-rGOFU",
    b"zTYG1N`q9OhPU7LE^zYG-gke!yuAFrSCM}+O|FSXt)KO|f&O2h$Cdd=(;T5RXSfFaZ!QXRhVr>b^W>q!",
    b">8Jj1J|BMimAj!)WA9?qg!`5>>0K(C^qvGw$c3)SG97DTF4NzB_<^bqR-|8lyC72jE1f%5OwwAFsFjn;",
    b"tC0;`C4ee%4f<S?VLrETo>Dk@n`RK^iKXIZk_jgdxZJ_gl)(}*V%Fg5WWiE0T)yC35Eso9L?x3i{`<#l",
    b"JeB6@&2S7R<#NjRlzuzF8Gql3Ie}#gN~66NWxY_el_U}I;{EXU*m;}rkheBNh+8e*@{mPVR2rJ>p)lg!",
    b"Fr|Ja?aELbpt9_>$=hTBCTUp72$VA0XL>vC=~T(DLNyBdZdps>N+WKqXK6|=+!2WK#zatJQ~0|O3&SzD",
    b"_#@kkf`24z;jgI^O}?jY7XD#6F&f_cK)z*r74WZYZvg>K_X3bN@!CCUhjdB2dL-#|iztbO_ubXgD@Gmj",
    b"A4s*bA5zT<pql}-pty*<RB>~rI;DLjN{hI%o=0a<Np0#ZBH!ukA46wxMCEyO7M0Yd&LZ-E44vg`jRqJZ",
    b"j?34t-D*>pkF)ttliBb(xlHBbbYaY{{(*XcFoB7GlEpe4FSXE2yiX1TU}0&=(URmxw#l1x84Wn0fh6Ze",
    b"_<ZFB)>f*+{XCqkbo7LmXsj(Hkcz(CnQjO#G;y*m;?b&8ADvR<`pAsBH$bO)PJL{un>0YCdtZI@#3a;5",
    b"OiW6B#N3QD!KEx$19Zl2DdXq;wy~zLB${XoL!oY~G01gWjzMnFdMtjUCJ?M~%{mBnyPk~_(VLhmfl335",
    b"CD3T3jv|!?8YvKIV8%omO{|$frDpdK@DJ6l`kh2VqJgCosWj?sqL-67Z*{0JUQrVYycgA|*YQLebr_yV",
    b"16AiqG-_ahNTc=@ywfI)!??`#%qff7q){0P4a_Km-$)}^3JuIBL!f~^vG`5QCPSg7$zyQqn>!A@K~G>Q",
    b"lyrk+R;A^)zYb+#gVAg_(HA4VPo_ICn@l2l@wR{-A|cGOMgC079q^MV{EVJR<w#ZQ4U$m8Xg*sk;()>g",
    b"-w`{U&;(FXXpZNi&de=MX7yw0fWS2l-Hwm@_IqBBt1y{qUr<wZG9g4L`ICu$vn&mEB+|u^j#SWbm;=iw",
    b"dGgw08&p;CDzzx%Ol8wOC9&+N7VT#j8xsvmr}asg0I+XU#itlqO~-N4ghG;8Z;_Hr3ru?#bKA0PCkeTK",
    b"ncE^mDCJemms&YEB%@2!y)R_bmN6Vniq~_ga7c0(U2YLXwL@S`uq1#k*`JUuu3!Mt!40`>5Gnrq-=H_>",
    b";SU)ttg(?3J(b#vYz--;aHOy%&k$#ZUT4>&EBys$YC!@-0}iJ2(94ICbV?hU!99$^KBE=61{4O&*jg6u",
    b"aqG#)KPk3k-(DSbem7w)Txz?b3Z8s7qzY!~mPQo<)LugsaM?yjCA@;Yk43mt2Oz0ARN>eZ9tv0`TW1?%",
    b"$1!>ZbZM570=&dzi0Ns{;j?TvieP+FoC37Oj!_AD3IKCkbywO4b2uiAO(iswZl@Aj$hf17K{D@DLept}",
    b"DuLtlJw;%QWluBgC;<zJb!ua!`FfNPg}gy^u&Uab#bI*-QNvH=Dh}m@)LPL=JRdG>u1uOtxHxAeaj{hA",
    b"FMAJ-=n*$}NxX^pKu%BV#cZN4@zEUV(9X?LSXOyAhN>aiaGiS%r7klgE_y=x;u0GTk$a5lHqCrU)-hAr",
    b"Vb2V>W#<FrfPzOMhoXH42BN@AU|`Dq0S1&F`I#5eF`k7e8qF!+wd_!e0$kF?m3CmGKRg*qdqvV2%KJd}",
    b"r%#Y#H0e)x{?xcn;Z4-UlTOCpynkJ&cQAep=%7y4k9~1gLdihiqjMzZ;z5SD03Z<?Z`4!h-~F|eO8mS6",
    b"nMtxNCBs7`&04}unxeUgE9!j(G1?=N5o6z{#5g_58@8|5rZu#NU&}Zl(@gh}xAH+p+T-JtQn@_q4v11?",
    b"P+~@Ebp6WKpw@&6TOzAYSsO^K%-d!IH@6yc7+YmlkXS$}P?5(e=oJ_`OhV5pY45Ox{xhrZY4Sy;j_Jet",
    b"O+fUXi-n{|>We}m&m4~DqgdME0s0pTxE&hzr^%Ov{c*61hV7#M&k<UbEer^)(5(wJT^AsyvXz$wWb^C0",
    b"y%&2CP4`Li4iq!T?p5C1gkX|`%RNoHHp)}1yz1$2iUl`A9hWeDk(5aJh{H*}<r*{va6FhEQ6O*n_>Dk?",
    b"HHm15G%{66=jH|)I`=r16!ufP$UI&UqNvWtUt>;>a3rN2YXD<qa_sRdr(QOE-QnRY2kl0$R@SU}33nrt",
    b"I5IUq4fr}8%SC<1@(<z(qKWIGSH}aauUlpm1<raO5pBtSlq#5@j##%cjuH!)QX1fI_=rxo```d0OH0$+",
    b"Zvi$V!V9D$VipV4Q$uOS8)KpWbEQv5x-pv@quFHjVXEvNQ&W3p>qEh6k{A#>ulAuA+$4dM#Q&nE3Qbnr",
    b"{`PJ%yBbdZP8dZ0q^TM9A-?h?_j>twOmX;!VYL?&A7LvE_0VnIWU(v{Mo|&20RPX012Z;?Dp)~@tyLBy",
    b"Jr1=r(0Uwd$E|4+@};S%Plv<^8l{SoDN!<*hXee@a#0V!DlYUL5m70gCz;ns=RV5woP=Ein@qgWkZ@n^",
    b"`>PLBoJ0=suQ*cZzh|1P^ouINpSMjjB%S-fD~!CH0LWqNx7h>(3$Q5VmyqR)w%ixpyhu7PDs>Xdvd^7F",
    b"hmKoZxzD_U{*wBbsQteCUeVJ`5-`>ey5^*r<=J@WTl~ZFw_DS*wd|_ohr|O5HGsFUQNzZg6K&!Ra0tQ;",
    b"4d`K_cKqYc4=iY>wZk2gkJa{-cBDuz>%lL+LI2?7(qh^H{FM5Pfk+<e^6jOyxWLWYOT0gZjcid+lO#tK",
    b"lV^)3ZW6Zf1f&l0McaNP_x7|TK2;7*S9FqnRRtIMv@JqKPEJmgmD|R|t9@D$WnE5ARx1m(1s31()3R>X",
    b"<LBhWTC^!qa??*sf>h<;^h8&(TT_1ZPg@eK$H>VElG`yWUj5UO+{(*66)`F8=Z)Ey-V1bG;T^=yd5Dx&",
    b"2-yum&neJSUQTw5mT&Pdyez2Y5xNdH&o5HNKx&;6y`o%_Ic=JbGL47|kFBk(5MmY3sL8PaEXn$h1|%#d",
    b"^Zq{G_mpOK%>uPr56tG*`W#$+0ul(xK?Od7ldS&;oRX>gMZ6;g(e>$NM3oeZ6gOm%l4361ni7+hD5tnT",
    b"2X*v7<dMV`L?M$!&*F3ys?>3qB8gJeErQmwz<*4ys$dt}Nu+~%TfRLgz5yHW^QL(@c(qtwvzJ{lE;)f8",
    b"$LOR-(Yo_fXLEjv+F#N|<D2fEolh1<e4}4+ESH=Tsk}Ak$2Y(I=fAr5pCt",
)


def _decode_payload() -> tuple[tuple[str, ...], tuple[str, ...]]:
    compressed = base64.b85decode(b"".join(_PAYLOAD_B85))
    decompressor = zlib.decompressobj()
    raw = decompressor.decompress(compressed, _MAX_PAYLOAD_BYTES + 1)
    if decompressor.unconsumed_tail or not decompressor.eof or decompressor.unused_data:
        raise RuntimeError("ST0306_PAYLOAD_COMPRESSION_INVALID")
    if len(raw) > _MAX_PAYLOAD_BYTES:
        raise RuntimeError("ST0306_PAYLOAD_TOO_LARGE")
    if hashlib.sha256(raw).hexdigest() != _PAYLOAD_SHA256:
        raise RuntimeError("ST0306_PAYLOAD_DIGEST_MISMATCH")
    value: Any = json.loads(raw)
    if not isinstance(value, dict) or set(value) != {"upgrade", "downgrade"}:
        raise RuntimeError("ST0306_PAYLOAD_SHAPE_INVALID")
    upgrade = value["upgrade"]
    downgrade = value["downgrade"]
    if (
        not isinstance(upgrade, list)
        or not isinstance(downgrade, list)
        or not all(isinstance(item, str) for item in (*upgrade, *downgrade))
    ):
        raise RuntimeError("ST0306_PAYLOAD_STATEMENTS_INVALID")
    return tuple(upgrade), tuple(downgrade)


UPGRADE_STATEMENTS, DOWNGRADE_STATEMENTS = _decode_payload()


def _execute(statements: tuple[str, ...]) -> None:
    connection = op.get_bind().execution_options(no_parameters=True)
    for statement in statements:
        connection.exec_driver_sql(statement)


def upgrade() -> None:
    _execute(UPGRADE_STATEMENTS)


def downgrade() -> None:
    _execute(DOWNGRADE_STATEMENTS)
