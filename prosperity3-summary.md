## Round 1 — Squid Ink, Resin, Kelp

**Rainforest Resin** was the simplest asset in the competition and behaved almost like a fixed-fair-value product. In practice, it was close to a pure market-making asset: the edge did not come from forecasting large directional moves, but from buying below fair value, selling above fair value, and managing inventory efficiently. Because of its stability, it was one of the cleanest products for learning basic quoting logic and position control. Public Prosperity 3 write-ups consistently list Resin as one of the three basic Round 1 assets.

**Kelp** was more dynamic than Rainforest Resin but still relatively structured. It can be viewed as an asset with a slowly moving fair value, where market making remained viable provided quotes were adjusted to a changing reference price. The main challenge was not extreme volatility, but fair-value estimation and quote placement. In that sense, Kelp sat between a fixed-value product and a more microstructure-driven one. Public team write-ups place Kelp alongside Resin and Squid Ink as the core Round 1 products.

**Squid Ink** was the most visibly volatile asset in the early stages of the competition. Its price behavior was characterized by aggressive spikes and sharp short-term dislocations. The main challenge was to determine whether these spikes represented genuine continuation or temporary deviations from fair value.

A useful interpretation was to treat Squid Ink as a **mean-reverting but highly volatile asset**. In practice, this meant that sudden upward or downward moves often created trading opportunities in the opposite direction, provided the move was sufficiently extreme and unsupported by broader market structure. Trend-localization tools such as **exponential moving averages (EMAs)** and **simple moving averages (SMAs)** were useful not because the asset was strongly trending, but because they helped identify when price had overextended relative to a local reference level.

Volatility analysis was especially important in this round. Plotting realized volatility or simply inspecting the amplitude and frequency of spikes was often enough to understand whether a move was exceptional or simply normal noise for the asset. Because of the large and abrupt fluctuations, position sizing and execution discipline were at least as important as directional forecasting.

## Round 2 — Picnic Baskets

This round introduced five new products:

- **Croissants (C)**
    
- **Jams (J)**
    
- **Djembes (D)**
    
- **Picnic Basket 1 = 6C + 3J + 1D**
    
- **Picnic Basket 2 = 4C + 2J**
    

The key idea of the round was to treat the baskets as ETF-like products and compare their market prices to their theoretical values implied by the constituents. For each basket, one can define:

$$
P^{\text{theo}}_t = \sum_i w_i P^i_t  
$$
and the corresponding premium or spread:

$$
\text{spread}_t = P^{ETF}_t - P^{\text{theo}}_t  
$$
This construction isolates the relative mispricing of the basket from the outright directional exposure of the underlying assets. In other words, instead of being exposed to Croissants, Jams, and Djembes themselves, the trader becomes exposed primarily to the **premium**.

A natural next step is to test whether this premium is mean-reverting. One standard way to do so is with a **Dickey-Fuller test**, and in our analysis both basket premiums appeared to be stationary or at least strongly mean-reverting. That makes the spread itself the natural trading object.

A common implementation is to normalize the spread using a rolling z-score:
$$
z_t = \frac{\text{premium}_t - \mu}{\sigma_{\text{rolling}}}  
$$
A basic strategy is then:

- if $z_t > 2$: short the ETF and long the basket
    
- if $z_t < -2$: long the ETF and short the basket

This is the canonical ETF statistical arbitrage framework.

A critical issue in this round was **overfitting**. If small changes in lookback windows, thresholds, or hedge ratios lead to large changes in PnL, the strategy is probably too fragile. Any signal based on premium reversion should be tested for robustness across parameter perturbations.

It is also worth noting the alternative approach reportedly used by Frankfurt Hedgehogs. Rather than normalizing by rolling volatility, they assumed volatility was approximately constant:

$$
\sigma_t \approx c  
$$

Under that assumption, the z-score adds little value, and one can work directly with fixed spread thresholds. This approach is sensible if the spread is stable, the variance is nearly constant, and the trading horizon is short enough that volatility regimes do not change materially.

They also incorporated an identified informed trader into the execution logic by dynamically shifting thresholds depending on that trader’s position. In addition, they continuously tracked the spread mean in live trading:

$$
\text{spread}_t = P^{ETF}_t - P^{\text{theo}}_t  
$$
$$
\text{adjusted spread}_t = \text{spread}_t - \mu  
$$
This is effectively a running premium adjustment.

Another refinement is **partial hedging**. Instead of fully hedging the ETF against the theoretical basket, it may be preferable to hedge only part of the risk, for example 50%. The rationale is that a fully hedged position may neutralize not only unwanted market exposure but also part of the alpha itself. Similarly, although the classical approach is to close the trade when the spread overshoots to the opposite side, it can be more robust to exit when the spread simply returns to zero. This reduces per-trade profit but often increases consistency and lowers variance.

## Round 3 — Volcanic Rock

This round introduced the most conceptually complex products of the competition: **Volcanic Rock** and various option-like instruments written on it. The essential financial concept is that an option gives the holder the right, but not the obligation, to buy the underlying asset at a fixed strike before expiration. The premium paid for this right is what must be priced correctly.

This is fundamentally an **option pricing** problem. The standard theoretical benchmark is the **Black-Scholes model**, from which the main option sensitivities, or Greeks, are derived:

- **Delta $\Delta$**: sensitivity of option price to the underlying
    
- **Gamma $\Gamma$**: sensitivity of delta to the underlying
    
- **Vega $\mathcal{V}$**: sensitivity to volatility
    
- **Theta $\Theta$**: time decay
    

The key concept in this round was **implied volatility**. Given a market price for an option, one can invert the Black-Scholes formula to recover the volatility that makes the model price equal to the market price. Across strikes, this gives rise to the **volatility smile**, which is central to identifying relative mispricings.

A reasonable workflow is therefore:

1. infer implied volatility from observed option prices,
    
2. model the volatility smile as a function of strike and maturity,
    
3. reprice the options using the fitted volatility surface,
    
4. identify overpriced and underpriced options relative to the fitted model.
    

That creates a volatility-relative-value strategy rather than a simple directional one.

Another important idea in this round is **delta hedging**, which aims to remove first-order exposure to the underlying by trading the appropriate quantity of Volcanic Rock against the options position. In principle, this creates a position that is locally neutral to small movements in spot. However, hedging is not always optimal in practice. If hedge execution is expensive and the underlying risk is modest, full delta hedging may reduce expected returns more than it reduces meaningful risk. In that setting, one should explicitly compare the cost of hedging against the reduction in exposure, potentially using a simple risk metric such as VaR.

Frankfurt Hedgehogs reportedly used a lightweight mean reversion logic rather than an overly elaborate volatility framework. That is consistent with a broader pattern in the competition: simplicity and robustness often dominated theoretical completeness.

## Round 4 — Magnificent Macarons

This round introduced Magnificent Macarons, an asset tradable across two islands through an import-export mechanism. Trading between islands involved **tariffs**, and for long positions there was an additional **storage tariff**. Since import tariffs were negative while export tariffs worked in the opposite direction, the primary opportunity was effectively to **import assets profitably**.

An especially important feature of the simulation was the presence of an **aggressive buyer**. This buyer would purchase any quantity of macarons below a certain threshold price, creating an exploitable local demand source. One profitable strategy was to sell locally to this buyer, temporarily build a short position, and then use the conversion mechanism each timestep to close or monetize that exposure.

Initially, a conservative implementation limited sales and conversions to 10 units per timestep. However, because the aggressive buyer was not always present, this cap left substantial profit unrealized. A more effective approach was to increase the sell size to 30 units per timestep, thereby creating a controlled short inventory buffer. This allowed the strategy to continue converting and realizing arbitrage gains even when no buyer appeared in a particular timestep. The result was a significant increase in traded volume and total PnL, at the cost of a relatively small increase in worst-case inventory risk.

This round was therefore not only about detecting arbitrage, but also about **execution optimization**. There was a meaningful trade-off between:

- posting at higher prices and earning more per fill,
    
- versus posting more aggressively and maximizing execution probability.
    

This is a classic market design problem: optimizing expected profit per order rather than only identifying a theoretical spread.

There was also additional exogenous information, most notably **Sunlight**, which appeared statistically significant in some modeling attempts. In our analysis, p-values in simple regressions were near zero, suggesting real explanatory power. However, in practice, that signal appeared less important than the direct import/export arbitrage itself. The dominant source of profit in this round came from exploiting the conversion mechanism and the aggressive local buyer, not from building a full exogenous forecasting model.

---

## Round 5 — Trader IDs Revealed

In the final round, the major new source of information was the revelation of trader identities. This made it possible to classify counterparties into economically meaningful groups:

- **Noise traders**: trade randomly, no informational content
    
- **Market makers**: provide liquidity around fair value
    
- **Informed traders**: trade based on private or superior information
    

This classification matters because copying behavior is only profitable if the source of the behavior is informative. Following market makers is usually useless, since they are not expressing directional conviction; they are monetizing the spread and managing inventory. Noise traders are also uninformative. In contrast, informed traders provide a potentially valuable directional signal.

The natural strategy in this round was therefore to identify the insider and selectively follow that flow, especially in assets where the signal was strongest. In our case, Croissants appeared to offer the most attractive exposure, so it made sense to maximize profit there while continuing to hedge basket-related risks and maintain market making activity in assets such as Kelp and Squid Ink.

Even in this final round, standard diagnostics remained useful: z-score behavior, premium correlations, and cross-asset relationships all helped distinguish genuine informed flow from random activity.

# Manual Trading Summary

## Round 1

The first manual round was a graph optimization problem involving currencies. There were four currencies, twelve directed exchange rates, and a maximum of five trades. The problem was essentially to find the best path through the exchange graph to maximize terminal wealth.

## Round 2

This round involved choosing a shipping container with a fixed PnL multiplier but substantial sensitivity to how many other participants selected the same container. A game-theoretic approach based on **Nash equilibrium** was attractive, although one had to be careful not to overcommit to a model with overly strong assumptions. In some cases, introducing randomization was a reasonable way to avoid becoming too predictable.

## Round 3

This round featured two bidding options with uniformly distributed values. The first had no penalty, while the second imposed a cubic penalty when bidding below the mean and a linear payoff structure above it. The key was to model the prior distribution correctly and avoid unjustified assumptions.

## Round 4

This was conceptually similar to the shipping container problem, but with more units and richer participant behavior. A useful approach was to define priors over different player types, such as griefers, Nash-equilibrium followers, and players biased toward round numbers, then use those priors to guide the final decision.

## Round 5

The final manual round was a portfolio optimization problem. The natural solution framework was optimization under uncertainty, with particular attention paid to prior assumptions and how sensitive the final allocation was to them.

# General Lessons from Prosperity 3

Across all rounds, a few principles repeatedly appeared:

1. **Simple, robust strategies often dominated more elaborate ones.**
    
2. **Execution and inventory management mattered as much as raw signal quality.**
    
3. **Mean reversion, when present, was most useful when tied to a clear structural object** such as a spread, premium, or implied mispricing.
    
4. **Overfitting was a constant danger**, especially when tuning thresholds, windows, or hedge ratios.
    
5. **External or hidden information sources**, such as trader IDs or special liquidity providers, could completely change what mattered in a given round.
