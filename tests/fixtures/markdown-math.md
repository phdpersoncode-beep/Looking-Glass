# Reconstruction

$$
R_0(H,p_T)=
\begin{cases}
\dfrac{v_I}{v_H+v_T-v_I}, & \text{valid completed reconstruction},\\
0, & \text{invalid or unfinished reconstruction},
\end{cases}
$$

where $v_H=\operatorname{Vol}(M_H)$, $v_T=\operatorname{Vol}(M_T)$, and $v_I=\operatorname{Vol}(M_H\cap M_T)$.

| Parameter | Meaning | Illustrative setting |
| --- | --- | ---: |
| $R$ | Independent roots/observations | 4 |
| $B$ | Surviving unfinished prefixes per root | 4 |
| $K$ | Independent next-block proposals per parent prefix | 4 |

$$
s_{r,t}=(X,Z_r,p_t),\qquad
p_{t+1}=p_t\mathbin{\Vert}a_t.
$$
