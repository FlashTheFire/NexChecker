**Zomato UI/UX Audit + Technical Engineering Blueprint for Pixel-Perfect Cloning**

This audit synthesizes Zomato’s public design system work (Sushi, 2019–2021 blogs), brand guidelines, current visual language observed across public analyses, and checkout flow patterns documented in multiple UX teardowns. Note: Direct live access to zomato.com was blocked in the analysis environment (HTTP/2 protocol errors), so findings rely on official Zomato engineering blogs, brand kits, and high-quality third-party reverse-engineering of the current product surface.

### 1. Design System Foundations (Sushi)

Zomato built **Sushi** on Atomic Design principles (atoms → molecules → organisms → templates → pages). Foundations are deliberately constrained for consistency and speed.

**Color Tokens (Primary System)**  
Core brand red is **Cranberry / Tomato Red** `#E23744` (also referenced as `#D94148` or `#CB202D` in some brand extractions; treat `#E23744` as the canonical primary). Supporting palette:

| Token | Hex | Role |
|-------|-----|------|
| `red-500` / brand | `#E23744` | CTAs, logo, key accents, non-veg |
| `red-600` / pressed | `#CB202D` | Active/pressed states |
| `red-100` | `#F9E5E7` | Soft backgrounds, badges |
| `green-500` | `#3AB757` | Veg indicator, success |
| `green-700` | `#1A8D37` | Pure veg / strong success |
| `gold` | `#EEA61B` | Ratings, Gold membership |
| `gray-50` | `#F8F8F8` / `#F4F4F2` | Page background (Tyrolean) |
| `gray-100` | `#F0F0F0` | Card surfaces |
| `gray-400` | `#9C9C9C` | Secondary text |
| `gray-700` | `#3E4152` | Body text |
| `gray-900` | `#1C1C1C` / `#2D2D2D` | Headings, primary text |
| White | `#FFFFFF` | Surfaces |

Colors were generated via HSL scales (100–900 naming) and validated against WCAG 2.0. Red is used sparingly for high-intent actions; green for dietary confirmation and success.

**Typography (Okra)**  
Okra is a modified open-source geometric sans (based on Metropolis). Scale used in Sushi:

`11, 12, 13, 15, 17, 19, 21, 24, 27` px

Weights: ExtraLight → ExtraBold (Regular for 11–19px body; Bold for primary headlines). Line-height typically ~1.4–1.5×. Responsive mapping exists (mobile 13px → web ~16px equivalents). Naming follows semantic or numbered scales (Display-100 style) for extensibility.

**Spacing Scale**  
Finalized at: `2, 4, 6, 8, 12, 16, 24, 32` (multiples/factors of an 8-point baseline). This is the primary rhythm for padding, margins, and gaps.

**Other Foundations**  
- Icons: Unified “Wasabi” library (SVG → icon font via Fontello) for cross-platform consistency.  
- Shadows: Soft, low-elevation (`0 2px 8px rgba(0,0,0,0.04)` resting; stronger on hover).  
- Border radius: Commonly 8–16px on cards; tighter (4–6px) on badges and chips.  
- Veg/Non-veg indicators: Cultural first-class citizens — green square + filled circle (veg); red square + triangle (non-veg). Size ~18px with 2px border.

### 2. Layout & Visual Hierarchy Audit

**Homepage / Discovery**  
- Sticky header with location selector + search.  
- “What’s on your mind” horizontal cuisine carousel (high visual weight, large food photography).  
- Filter chips (Delivery / Dining / Offers / etc.) and vertical restaurant feed.  
- Restaurant cards are the core organism: 16:9 (or similar) hero image with overlays (discount badge bottom-left, ETA bottom-right), restaurant name (bold 17px), rating badge (green), cuisine + price-for-two + distance meta row.  
- Information density is high but scannable due to strict visual hierarchy and generous card internal padding (12–16px).

**Restaurant / Menu**  
- Large hero + sticky tabs for categories.  
- Menu items: left image or indicator + name + description + price + add button. Customization modals are frequent friction points.

**Strengths**  
- Strong brand recognition via red + high-quality food photography.  
- Personality-driven microcopy and illustrations reduce anxiety (loading, empty, error states).  
- Persistent bottom cart bar after first add keeps purchase intent visible.  
- Smart defaults (recent address, saved payments) reduce steps for returning users.

**Weaknesses / Friction**  
- Homepage can feel banner-heavy / chip-overloaded (cognitive load).  
- Restaurant cards sometimes bury secondary signals.  
- Visual hierarchy on payment selection has historically been weak (users miss “Pay Using” vs primary CTA).

### 3. Checkout Friction Points (Critical Path)

Documented patterns and issues from multiple 2025–2026 teardowns:

**Positive Patterns**  
- Persistent “View Cart” bar with item count + total.  
- Aggressive smart defaults (last address, preferred payment).  
- Fee transparency improved over time (bill breakdown earlier).  
- Single-screen compression of address + payment + summary in mature versions.  
- Trust cues (delivery partner name, ratings, live tracking later).

**Friction & Drop-off Drivers**  
1. **Late / surprise fees** — Delivery, platform, packaging, and taxes revealed late create expectation mismatch (menu price anchoring).  
2. **Multi-step or modal-heavy customization** — Adding an item → customization → back to full menu feels discontinuous.  
3. **Payment CTA hierarchy** — Primary “Place Order” sometimes visually dominates the payment method selector, leading to accidental submissions or failed transactions.  
4. **Address friction for new users** — Location detection helps, but manual entry + validation can be lengthy.  
5. **Cart editing** — Leaving checkout to edit items increases abandonment.  
6. **Coupon discovery** — Offers sometimes feel buried relative to the final price.  
7. Occasional UI bugs (stacked previous-restaurant cart overlapping CTA) reported as P0-level.

**Net Effect**: High-intent users still abandon when price jumps or when cognitive load spikes at the final decision point. Transparency + fewer steps + visible progress are the highest-leverage improvements.

### 4. Technical Engineering Blueprint — React + Tailwind Clone

Goal: Component architecture and recipes that can pixel-match any Zomato surface when fed the correct data and assets.

#### 4.1 Design Tokens (Tailwind Config / CSS Variables)

```js
// tailwind.config.js (excerpt)
module.exports = {
  theme: {
    extend: {
      colors: {
        zomato: {
          red: { DEFAULT: '#E23744', 600: '#CB202D', 100: '#F9E5E7' },
          green: { DEFAULT: '#3AB757', 700: '#1A8D37' },
          gold: '#EEA61B',
          gray: {
            50: '#F8F8F8', 100: '#F0F0F0', 400: '#9C9C9C',
            700: '#3E4152', 900: '#1C1C1C'
          }
        }
      },
      fontFamily: {
        okra: ['Okra', 'Metropolis', 'system-ui', 'sans-serif']
      },
      fontSize: {
        'z-11': '11px', 'z-12': '12px', 'z-13': '13px', 'z-15': '15px',
        'z-17': '17px', 'z-19': '19px', 'z-21': '21px', 'z-24': '24px', 'z-27': '27px'
      },
      spacing: {
        0.5: '2px', 1: '4px', 1.5: '6px', 2: '8px', 3: '12px',
        4: '16px', 6: '24px', 8: '32px'
      },
      borderRadius: {
        card: '16px', badge: '6px', chip: '8px'
      },
      boxShadow: {
        card: '0 2px 8px rgba(0,0,0,0.04)',
        'card-hover': '0 4px 16px rgba(0,0,0,0.08)'
      }
    }
  }
}
```

Use CSS variables for runtime theming if needed.

#### 4.2 Component Architecture (Atomic → Page)

```
atoms/
  Button, Icon, Badge, RatingPill, VegNonVegIndicator, Price, Avatar
molecules/
  SearchBar, FilterChip, QuantityStepper, DiscountBadge, DeliveryTimeBadge
organisms/
  RestaurantCard, MenuItemRow, CartBar, AddressSelector, BillBreakdown
  PaymentMethodList, CustomizationModal
templates/
  DiscoveryFeed, RestaurantMenu, CheckoutShell
pages/
  Home, Restaurant, Cart, Checkout, OrderTracking
```

**State Model (Zustand / Jotai / Redux Toolkit recommended)**  
- `cart`: items[], restaurantId, totals, appliedCoupon  
- `user`: addresses[], selectedAddressId, paymentMethods[]  
- `ui`: activeModal, isCartOpen, loadingStates  
- Derived: `cartItemCount`, `grandTotal`, `isMinOrderMet`

#### 4.3 Key Recipes

**RestaurantCard**
```tsx
<div className="bg-white rounded-card overflow-hidden shadow-card hover:shadow-card-hover transition-shadow duration-200 cursor-pointer">
  <div className="relative aspect-[16/9]">
    <img src={image} className="w-full h-full object-cover" />
    {discount && (
      <div className="absolute bottom-3 left-3 bg-[#2C365E] text-white px-2.5 py-1 rounded-badge text-z-13 font-bold">
        <span className="text-z-17 block">{discount.percent}% OFF</span>
        up to ₹{discount.max}
      </div>
    )}
    <div className="absolute bottom-3 right-3 bg-white/95 px-2 py-1 rounded-badge text-z-12 font-semibold">
      {eta} min
    </div>
  </div>
  <div className="p-3 px-4">
    <h3 className="text-z-17 font-bold text-zomato-gray-900 truncate">{name}</h3>
    <div className="flex items-center gap-2 mt-1">
      <span className="inline-flex items-center gap-1 bg-zomato-green-700 text-white px-1.5 py-0.5 rounded-badge text-z-12 font-bold">
        ★ {rating}
      </span>
      <span className="text-zomato-gray-400 text-z-13">{cuisines}</span>
    </div>
    <div className="flex items-center gap-2 text-zomato-gray-400 text-z-13 mt-1">
      <span>₹{priceForTwo} for two</span>
      <span className="w-0.5 h-0.5 rounded-full bg-current" />
      <span>{distance} km</span>
    </div>
  </div>
</div>
```

**Veg / Non-Veg Indicator**
```tsx
<span className={`inline-flex items-center justify-center w-[18px] h-[18px] border-2 rounded-[2px]
  ${isVeg ? 'border-zomato-green' : 'border-zomato-red'}`}>
  {isVeg 
    ? <span className="w-2 h-2 rounded-full bg-zomato-green" />
    : <span className="w-0 h-0 border-l-[5px] border-r-[5px] border-b-[8px] border-l-transparent border-r-transparent border-b-zomato-red" />
  }
</span>
```

**Persistent Cart Bar (Micro-interaction)**
```tsx
// Appears with spring animation when cart.length > 0
<div className="fixed bottom-0 inset-x-0 z-50 px-4 pb-4 safe-area">
  <button 
    onClick={openCart}
    className="w-full bg-zomato-red text-white rounded-xl py-3.5 px-4 flex items-center justify-between shadow-lg
               active:scale-[0.98] transition-transform"
  >
    <span className="font-semibold">{itemCount} items</span>
    <span className="font-bold">View Cart • ₹{total}</span>
  </button>
</div>
```

**Checkout Shell (Friction-Reduced)**  
- Single primary column on mobile; two-column on desktop (summary sticky).  
- Always-visible bill breakdown (items + delivery + taxes + discounts).  
- Address and payment as expandable cards with clear “Change” affordances.  
- Primary CTA text: `Place Order • ₹{finalAmount}` (includes total).  
- Inline validation + optimistic updates for coupon application.

#### 4.4 State-Driven Micro-Interactions

- **Add to cart**: Quantity stepper appears with scale + opacity; bottom bar slides up with spring (`framer-motion` or CSS `@keyframes` + `transition`).  
- **Card hover**: Shadow elevation only (no scale to avoid layout shift).  
- **Loading / empty states**: Personality microcopy + illustration (keep the brand voice).  
- **Price change / coupon**: Subtle highlight pulse on the total.  
- **Success**: Confetti or check animation + clear next-step CTA (Track Order).  
- Prefer `prefers-reduced-motion` media query.

#### 4.5 Implementation Notes for Fidelity

- Use exact Okra/Metropolis font files (or closest system fallback + `font-feature-settings`).  
- Match image aspect ratios and object-fit precisely.  
- Implement infinite scroll / virtualized lists for restaurant feeds (react-window or TanStack Virtual).  
- Cart and checkout should be fully keyboard and screen-reader accessible (ARIA live regions for total updates).  
- For “any webpage” cloning: treat each major surface (Home, Search Results, Restaurant, Cart, Checkout, Tracking) as a composed template of the above organisms. Data shape should mirror Zomato’s public API patterns where possible (restaurant, menu, cart, order).

### Summary Recommendations

- **Clone priority order**: Design tokens → RestaurantCard + indicators → Persistent CartBar → Checkout shell with transparent pricing → Personality empty/loading states.  
- Highest UX ROI for any clone or improvement: early full-price visibility, one-tap address/payment defaults, and unmissable payment-method selection hierarchy.  
- Keep the red disciplined — it is the appetite and action signal, not decoration.

This blueprint gives a production-grade starting point that can be refined against live screenshots or Figma exports for true pixel parity. If you need code for a specific surface (e.g., full Checkout component tree, tracking map UI, or Tailwind plugin for the exact type scale), provide the target page and I will expand it.