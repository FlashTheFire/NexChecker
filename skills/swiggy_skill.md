**Swiggy UI/UX Audit + Technical Engineering Blueprint for Pixel-Perfect Cloning**

This audit draws from Swiggy’s official Design Language System (DLS), brand identity (signature orange + S-pin logo), public engineering posts, motion guidelines, and multiple checkout UX analyses. Swiggy optimizes for appetite-driven, high-velocity food ordering with strong multi-vertical support (Food, Instamart, Dineout, Genie).

### 1. Design System Foundations

Swiggy’s visual language is warm, energetic, and deliberately loud — designed to trigger craving and make ordering feel instantaneous. The hero color is an unmistakable orange.

**Color Tokens**  

| Token | Hex (approx.) | Role |
|-------|---------------|------|
| `swiggy-orange` / primary | `#FC8019` | Primary CTAs, active tabs, icons, brand accents, wordmark |
| Orange variants | Slightly darker/lighter | Hover, pressed, gradients (orange→red for offers) |
| Rating green | `#48C479` | High ratings |
| Rating amber | `#DB7C38` | Mid ratings |
| Error | `#E84A4A` | Errors, stock issues |
| Canvas / surfaces | White `#FFFFFF`, light grays, dark mode charcoal | Backgrounds, cards |
| Text | Near-black primary, secondary grays | Hierarchy |
| Vertical accents | Magenta-purple (Instamart), others for Dineout/Genie | Sub-brand differentiation |

Orange is the emotional and functional anchor; supporting colors handle trust (ratings) and status.

**Typography**  
Clean grotesque / Proxima-Nova lineage (or system SF Pro / Inter fallback). Heavy weights carry hierarchy: bold/extra-bold for food names and prices, medium for metadata. High legibility at small sizes for dense restaurant and menu cards.

**Spacing, Radius, Elevation**  
- Efficient 4/8-pt rhythm.  
- Border radius: 8–12 px on cards and buttons (friendly, modern).  
- Shadows: Subtle functional elevation; food imagery does most of the visual work.  
- Icons: Clear, high-recognition line/filled set (location pin, search, cart, veg/non-veg).

**Other Foundations**  
- Strong location + search header.  
- Veg (green) / Non-veg (red) indicators are first-class.  
- Offer chips with gradient or bold treatment.  
- Persistent cart bar and Slide-to-Pay pattern for intentional confirmation.

### 2. Layout & Visual Hierarchy Audit

**Homepage / Discovery**  
- Location + search dominant.  
- Vertical switcher (Food / Instamart / etc.).  
- Restaurant cards with image, name, rating, ETA, offers, cuisine tags.  
- Personalized shelves, “Reorder”, and promotional rails.

**Restaurant / Menu**  
- Sticky header with restaurant info and cart summary.  
- Category tabs, search within menu, veg filter.  
- Dish cards with image (optional), name, price, description, customisation, Add button + quantity stepper.  
- Strong visual weight on price, rating, and “Add”.

**Strengths**  
- Appetite-driven visual hierarchy — food imagery and orange CTAs dominate.  
- Fast path from discovery → restaurant → add → cart.  
- Clear rating and offer signaling.  
- Mature handling of customisation and veg/non-veg.

**Weaknesses**  
- Uni-cart limitation (cannot easily combine restaurants) creates friction versus multi-cart competitors.  
- Dense promotional content can compete with core restaurant list.  
- Occasional cognitive load on complex customisation flows.

### 3. Checkout Friction Points

Swiggy has invested heavily in checkout (Slide-to-Pay, error handling, quick checkout experiments). Remaining friction is well-documented.

**Positive Patterns**  
- Persistent cart with live total.  
- Slide-to-Pay introduces healthy friction against accidental taps while preserving conversion.  
- Improved error recovery (hard vs soft errors, payment retry flows).  
- Coupon and Swiggy One benefits surfaced clearly.  
- Address and payment method persistence for returning users.

**Key Friction & Drop-off Drivers**  
1. **Uni-cart constraint** — Users wanting items from multiple restaurants must abandon or complete one cart first.  
2. **Accidental taps** — Historically high; Slide-to-Pay was the deliberate solution.  
3. **Restaurant closure / stock errors** — Hard errors that can appear late; timer and proactive messaging help but still interrupt.  
4. **Payment failure recovery** — Earlier flows required restarting payment selection; improved but still a drop-off point.  
5. **Coupon application** — Discovery and application can feel secondary or require extra steps.  
6. **Customisation complexity** — Multi-step modifiers increase time-to-order for complex dishes.  
7. **Address / location edge cases** — Serviceability changes or map confirmation can add friction.  
8. **Fee transparency** — Delivery, packing, or surge fees surfacing late reduce trust.

Highest-ROI areas for clones: robust error states with clear recovery, intentional confirmation (slide or equivalent), early total + fee visibility, and strong reorder / “Buy Again” surfaces.

### 4. Technical Engineering Blueprint — React + Tailwind

#### 4.1 Design Tokens (Tailwind Config)

```js
// tailwind.config.js (excerpt)
module.exports = {
  theme: {
    extend: {
      colors: {
        swiggy: {
          orange: { DEFAULT: '#FC8019', dark: '#E06E0F', light: '#FD9A45' },
          rating: { high: '#48C479', mid: '#DB7C38' },
          error: '#E84A4A',
          ink: '#02060C',
          gray: {
            50: '#F4F4F6', 100: '#ECECEE', 200: '#E2E2E7',
            400: '#686B78', 600: '#4A4D57', 900: '#1C1C1E'
          }
        }
      },
      fontFamily: {
        sans: ['Proxima Nova', 'Inter', 'system-ui', 'sans-serif']
      },
      fontSize: {
        'sw-xs': '12px', 'sw-sm': '13px', 'sw-base': '14px',
        'sw-md': '16px', 'sw-lg': '18px', 'sw-xl': '20px'
      },
      spacing: {
        0.5: '2px', 1: '4px', 1.5: '6px', 2: '8px', 3: '12px',
        4: '16px', 5: '20px', 6: '24px'
      },
      borderRadius: {
        btn: '8px', card: '12px', chip: '8px'
      },
      boxShadow: {
        card: '0 1px 4px rgba(2,6,12,0.06)',
        elevated: '0 4px 12px rgba(2,6,12,0.1)'
      }
    }
  }
}
```

#### 4.2 Component Architecture

```
atoms/
  Button, Icon, Badge, Price, QuantityStepper, VegIndicator, RatingStars
molecules/
  SearchBar, OfferChip, ETABadge, CategoryTab, SizeOrCustomisationChip
organisms/
  RestaurantCard, DishCard, MenuSection, Header, CartItem,
  AddressCard, BillSummary, StickyCartBar, SlideToPay
templates/
  HomeFeed, RestaurantMenu, Cart, CheckoutFlow, OrderTracking
pages/
  Home, Search, Restaurant, Cart, Checkout, Tracking
```

**State Model** (Zustand recommended)  
- `cart`: items[] (with customisations), restaurantId, appliedCoupon  
- `user`: addresses[], paymentMethods[], swiggyOneStatus  
- `ui`: activeVertical, isCartOpen, selectedCustomisations, etaMinutes  
- Derived: `itemCount`, `subtotal`, `grandTotal`, `deliveryFee`, `isSlideReady`

#### 4.3 Key Recipes

**RestaurantCard**
```tsx
<div className="bg-white rounded-card shadow-card overflow-hidden">
  <div className="relative aspect-[16/10]">
    <img src={image} className="w-full h-full object-cover" />
    {offer && (
      <span className="absolute bottom-2 left-2 bg-gradient-to-r from-swiggy-orange to-red-500 
                       text-white text-sw-xs font-bold px-2 py-0.5 rounded">
        {offer}
      </span>
    )}
  </div>
  <div className="p-3">
    <div className="flex items-start justify-between gap-2">
      <h3 className="text-sw-md font-bold text-swiggy-ink line-clamp-1">{name}</h3>
      <div className="flex items-center gap-1 bg-swiggy-rating-high text-white text-sw-xs px-1.5 py-0.5 rounded">
        ★ {rating}
      </div>
    </div>
    <p className="text-sw-xs text-swiggy-gray-400 mt-0.5">{cuisines}</p>
    <div className="flex items-center gap-2 mt-1 text-sw-xs text-swiggy-gray-600">
      <span>{eta} mins</span>
      <span>•</span>
      <span>₹{costForTwo} for two</span>
    </div>
  </div>
</div>
```

**DishCard + Veg Indicator**
```tsx
<div className="flex gap-3 py-3 border-b border-swiggy-gray-100">
  <div className="flex-1">
    <div className="flex items-center gap-1.5">
      <VegIndicator isVeg={isVeg} />
      <h4 className="text-sw-sm font-semibold text-swiggy-ink">{name}</h4>
    </div>
    <p className="text-sw-sm font-bold mt-0.5">₹{price}</p>
    <p className="text-sw-xs text-swiggy-gray-400 mt-1 line-clamp-2">{description}</p>
  </div>
  <div className="relative w-24 shrink-0">
    {image && <img src={image} className="w-full aspect-square object-cover rounded-lg" />}
    <button className="absolute -bottom-2 left-1/2 -translate-x-1/2 bg-white border border-swiggy-orange 
                       text-swiggy-orange font-bold text-sw-xs px-4 py-1.5 rounded-btn shadow-sm">
      ADD
    </button>
  </div>
</div>
```

**Sticky Cart Bar**
```tsx
<div className="fixed bottom-0 inset-x-0 bg-white border-t border-swiggy-gray-200 p-3 safe-area z-50">
  <div className="flex items-center justify-between gap-3 max-w-lg mx-auto">
    <div>
      <p className="text-sw-sm font-bold">₹{grandTotal}</p>
      <p className="text-sw-xs text-swiggy-gray-600">{itemCount} items</p>
    </div>
    <button className="flex-1 bg-swiggy-orange hover:bg-swiggy-orange-dark text-white font-semibold py-3 rounded-btn">
      View Cart
    </button>
  </div>
</div>
```

**Slide-to-Pay (Healthy Friction)**
```tsx
<div className="relative h-14 bg-swiggy-gray-100 rounded-btn overflow-hidden">
  <div className="absolute inset-y-0 left-0 bg-swiggy-orange transition-all" style={{ width: `${progress}%` }} />
  <div className="relative flex items-center justify-center h-full text-white font-semibold">
    {progress < 100 ? 'Slide to Pay' : 'Processing…'}
  </div>
  {/* Draggable thumb implementation with pointer events */}
</div>
```

#### 4.4 State-Driven Micro-Interactions

- **Add dish**: Button → quantity stepper appears + cart bar elevates with spring.  
- **Customisation sheet**: Bottom sheet with live price update.  
- **Slide-to-Pay**: Drag threshold triggers confirmation; haptic + success animation.  
- **Coupon apply**: Immediate total recalculation + savings highlight.  
- **Error states**: Soft errors (retry) vs hard errors (clear messaging + alternatives).  
- **ETA / status**: Live updates with subtle motion; avoid misleading perpetual “5 min”.  
- Prefer 150–250 ms transitions; respect `prefers-reduced-motion`.

#### 4.5 Implementation Notes for Fidelity

- Veg/Non-veg indicators and rating colors are non-negotiable for trust.  
- Support restaurant-level cart isolation (uni-cart model) or clearly design multi-cart if extending.  
- Virtualize long menus and restaurant lists.  
- Handle food-specific flows: customisation, cooking requests, cutlery, Swiggy One.  
- Checkout must surface full bill early and provide resilient payment recovery.  
- Accessibility: High contrast on orange, large targets for steppers and slide control, ARIA for live totals and status.  
- For “any webpage” cloning: Compose Home, Restaurant/Menu, Cart, Checkout, and Tracking from the organisms above.

### Summary Recommendations

- **Clone priority**: Tokens + RestaurantCard / DishCard with veg indicator → Sticky orange cart bar → Transparent Bill Summary → Slide-to-Pay (or equivalent intentional confirmation) → Robust error recovery.  
- Highest conversion ROI: Reduce late surprises (fees, stock, closure), keep totals visible, make confirmation intentional without excessive friction, and strengthen reorder surfaces.  
- Preserve the warm, craving-driven, high-energy personality — Swiggy wins on appetite and speed of path-to-order.

This blueprint provides a production-ready foundation for high-fidelity cloning of Swiggy surfaces. Specify a target page (Home, Restaurant Menu, Cart, Checkout, Tracking, Instamart, etc.) and I will expand the component tree, exact interaction recipes, or accessibility checklist.